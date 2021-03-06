#!/usr/bin/python
from libyate import Yate
from libvbts import YateMessenger
import logging
import sys
import re
import time
import random
import string
import re
import math

DTMF_TIME = 0.5 #seconds of wait between DTMF bursts

FILE_ROOT = "/usr/local/share/yate/sounds"

INTRO_FILE = FILE_ROOT + "/intro.gsm"

INPUT_FILE = FILE_ROOT + "/prompt.gsm"

VERIFY_START_FILE = FILE_ROOT + "/chosen.gsm"

VERIFY_END_FILE = FILE_ROOT + "/chosen2.gsm"

INVALID_FILE = FILE_ROOT + "/invalid.gsm"

ERROR_FILE = FILE_ROOT + "/error.gsm"

TAKEN_FILE = FILE_ROOT + "/taken.gsm"

EXIT_FILE = FILE_ROOT + "/exit.gsm"

NUMBER_FILES = { "1" : FILE_ROOT + "/one.gsm",
		 "2" : FILE_ROOT + "/two.gsm",
		 "3" : FILE_ROOT + "/three.gsm",
		 "4" : FILE_ROOT + "/four.gsm",
		 "5" : FILE_ROOT + "/five.gsm",
		 "6" : FILE_ROOT + "/six.gsm",
		 "7" : FILE_ROOT + "/seven.gsm",
		 "8" : FILE_ROOT + "/eight.gsm",
		 "9" : FILE_ROOT + "/nine.gsm",
		 "0" : FILE_ROOT + "/zero.gsm" }

def uniqid(size=6, chars=string.ascii_uppercase + string.digits):
	return ''.join(random.choice(chars) for x in range(size))

def random_num(minsize, maxsize):
	minnum = math.pow(10, minsize-1)
	maxnum = math.pow(10, maxsize) - 1
	return str(random.randint(minnum, maxnum))

class Provisioner:

	""" initialize the object """
	def __init__(self, to_be_handled):
		self.app = Yate()
		self.app.__Yatecall__ = self.yatecall
		self.log = logging.getLogger("libvbts.yate.VBTS_Call_Provisioning.Provisioner")
		self.ym =  YateMessenger.YateMessenger()
		self.to_be_handled = to_be_handled
		self.state = "call"
		self.ourcallid = "provisioner/" + uniqid(10)
		self.partycallid = ""
		self.last_dtmf = (None, 0.0)
		self.user_num = ""
		self.minnum = int(self.ym.smqueue_get("SC.Register.Digits.Min"))
		self.maxnum = int(self.ym.smqueue_get("SC.Register.Digits.Max"))
		self.log.info("Starting with min=%d and max=%d" % (self.minnum, self.maxnum))

	def __play(self, fileloc):
		self.app.Yate("chan.attach")
		self.app.params = []
		self.app.params.append(["source", "wave/play/" + fileloc])
		self.app.params.append(["notify", self.ourcallid])
		self.app.Dispatch()
		#not sure if this is needed
		self.app.Yate("chan.attach")
		self.app.params = []
		self.app.params.append(["consumer", "wave/record/-"])
		self.app.params.append(["maxlen", "320000"])
		self.app.params.append(["notify", self.ourcallid])
		self.app.Dispatch()
		self.transition = (0,[],"intro")
		return	

	def __next(self, index, files, nextState):
		self.transition = (index, files, nextState)

	def setState(self, state):
		self.app.Output("setState('%s') state: %s" % (self.state, state))

		if (state == ""):
			self.close()

		if (state == "intro"):
			self.state = state
			self.__play(INTRO_FILE)
			self.__next(1, [INTRO_FILE], "input")

		#if we get this, replay the prompt
		elif (state == "input"):
			self.state = state
			self.__play(INPUT_FILE)
			self.__next(1,[INPUT_FILE], "input")

		elif (state == "taken"):
			self.state = state
			self.user_num = ""
			self.__play(TAKEN_FILE)
			self.__next(1,[TAKEN_FILE], "input")

		elif (state == "invalid"):
			self.state = state
			self.user_num = ""
			self.__play(INVALID_FILE)
			self.__next(1,[INVALID_FILE], "input")

		elif (state == "exit"):
			self.state = state
			self.user_num = ""
			self.__play(EXIT_FILE)
			self.__next(1,[EXIT_FILE], "goodbye")

		elif (state == "error"):
			self.state = state
			self.user_num = ""
			self.__play(ERROR_FILE)
			self.__next(1,[ERROR_FILE], "input")

		elif (state == "verify"):
			#number taken
			self.app.Output(str(self.ym.SR_get("name", ("callerid", self.user_num))))
			if (self.ym.SR_get("name", ("callerid", self.user_num))):
				#don't set the state, transfer to taken instead
				self.setState("taken")
				return
			else:
				#want to play chosens and numbers here
				self.__play(VERIFY_START_FILE)
				audio = [VERIFY_START_FILE]
				for i in self.user_num:
					audio.append(NUMBER_FILES[i])
				audio.append(VERIFY_END_FILE)
				self.app.Output("Want to verify %s" % (self.user_num,))
				self.state = state
				self.__next(1,audio, "verify")
		
		elif (state == "goodbye"):
			self.state = state
			self.app.Yate("chan.attach")
			self.app.params = []
			self.app.params.append(["source","tone/congestion"])
			self.app.params.append(["consumer", "wave/record/-"])
			self.app.params.append(["maxlen", 32000])
			self.app.params.append(["notify", self.ourcallid])
			self.app.Dispatch()


	def gotNotify(self, reason):
		self.app.Output("gotNotify() state: %s" % (self.state,))

		if (reason == "replace"):
			return

		elif (reason == "goodbye"):
			self.setState("")

		elif (reason == "record" or reason == "play"):
			self.setState("input")

		elif (reason == "eof"):
			(index, files, nextState) = self.transition
			if (index >= len(files)):
				self.setState(nextState)
			else:
				self.__play(files[index])
				index += 1
				self.transition = (index, files, nextState)

	def gotDTMF(self, text):
		#if it's too recent, skip the dtmf burst
		if (text == self.last_dtmf[0] and time.time() < self.last_dtmf[1] + DTMF_TIME):
			self.last_dtmf = (text, time.time())
			return
		else:
			self.last_dtmf = (text, time.time())
		
		self.app.Output("gotDTMF('%s') state: %s" % (text, self.state));
		
		#else if we're in the verify step, should only get # or *
		if (self.state == "verify"):
			if (text == "#"):
				self.app.Output("Provisoning %s %s %s %s" % (self.name, self.user_num, self.ipaddr, self.port))
				self.log.info("Provisoning %s %s %s %s" % (self.name, self.user_num, self.ipaddr, self.port))
				if (self.ym.SR_provision(self.name, self.user_num, self.ipaddr, self.port)):
					self.ym.send_smqueue_sms(self.app, self.user_num, "101 <sip:101@127.0.0.1>", "Your Papa Legba Burning Man number is %s" % (self.user_num,))
					self.setState("exit")
				else:
					self.setState("error")
			elif (text == "*"):
				self.user_num = ""
				self.setState("input")
			else:
				self.setState("verify")

		#still inputting
		elif (self.state == "input"):
			if (text in string.digits):
				self.user_num += text
			elif (text == "#"):
				if ((len(self.user_num) >= self.minnum) and (len(self.user_num) <= self.maxnum)):
					self.setState("verify")
				else:
					self.log.info("Number %s is invalid" % self.user_num)
					self.setState("invalid")
			elif (text == "*"):
				#generate number for them
				self.user_num = random_num(self.minnum, self.maxnum)
				while (self.ym.SR_get("name", ("callerid", self.user_num))):
					self.user_num = random_num(self.minnum, self.maxnum)
				self.setState("verify")

		#we'll figure this out later
		else:
			self.user_num = ""
			self.setState("input")
			

	def yatecall(self, d):

		if d == "":
			self.app.Output("VBTS Provisioner event: empty")

		elif d == "incoming":
			self.app.Output("VBTS Provisioner Incoming: " +  self.app.name + " id: " + self.app.id)
			
			if (self.app.name == "call.execute"):
				if (not self.ym.is_imsi(self.ym.get_param("caller", self.app.params))):
					self.app.Acknowledge()
					return

				self.name = self.ym.get_param("caller", self.app.params)
				self.ipaddr = self.ym.get_param("ip_host", self.app.params)
				self.port = self.ym.get_param("ip_port", self.app.params)
				self.partycallid = self.ym.get_param("id", self.app.params)
				self.ym.add_param("targetid", self.ourcallid, self.app.params)
				self.app.handled = True


				#if this is being originated, we have to create next link
				target = self.ym.get_param("vbts_target", self.app.params)
				if (target):
					callername = self.ym.get_param("vbts_from", self.app.params)
					if not (callername):
						callername = "101"
					old_yate = self.app
					self.app.Yate("call.execute")
					self.app.params = []
					self.ym.add_param("id", self.partycallid, self.app.params)
					self.ym.add_param("callto", target, self.app.params)
					self.ym.add_param("caller", callername, self.app.params)
					#self.ym.add_param("tonedetect_out", "true", self.app.params)
					self.app.Dispatch()
					
					#finish with old message
					old_yate.Acknowledge()
				else:
					self.app.Acknowledge()

					#then respond
					self.app.Yate("call.answered")
					self.app.params = []
					self.ym.add_param("id", self.ourcallid, self.app.params)
					self.ym.add_param("targetid", self.partycallid, self.app.params)
					self.app.Dispatch()

				self.setState("intro")
				return

			elif (self.app.name == "chan.notify"):
				self.app.Output("VBTS Provisioner Notify: " +  self.app.name + " id: " + self.app.id)
				if (self.ym.get_param("targetid", self.app.params) in [self.ourcallid, self.partycallid]):
					self.gotNotify(self.ym.get_param("reason", self.app.params))
					self.app.handled = True
				self.app.Acknowledge()
				return

			elif (self.app.name == "chan.dtmf"):
				if (self.ym.get_param("targetid", self.app.params) in [self.ourcallid, self.partycallid]):
					text = self.ym.get_param("text", self.app.params)
					for t in text:
						self.gotDTMF(t)
					self.app.handled = True
				self.app.Acknowledge()
				return
			else:
				self.app.Output("WTF? " + self.app.name)
				self.app.Acknowledge()
				return

		elif d == "answer":
			self.app.Output("VBTS Provisioner Answered: " +  self.app.name + " id: " + self.app.id)
		elif d == "installed":
			self.app.Output("VBTS Provisioner Installed: " + self.app.name )
		elif d == "uninstalled":
			self.app.Output("VBTS Provisioner Uninstalled: " + self.app.name )
		else:
			self.app.Output("VBTS Provisioner event: " + self.app.type )
			
	def uninstall(self):
		for msg in self.to_be_handled:
			self.app.Uninstall(msg)

	def main(self):
		for msg in to_be_handled:
			self.app.Output("VBTS Provisioner Installing %s" % (msg,))
			self.log.info("Installing %s" % (msg,))
			self.app.Install(msg)
			
		try:
			while True:
				self.app.flush()
				time.sleep(0.1)

		except Exception as e:
			self.log.debug(str(e))
			self.close()

	def close(self):
		self.uninstall()
		self.app.close()
		exit(0)

if __name__ == '__main__':
	logging.basicConfig(filename="/var/log/VBTS.log", level="DEBUG")
	to_be_handled = ["chan.dtmf", "chan.notify"]
	vbts = Provisioner (to_be_handled)
	vbts.app.Output("VBTS Provisioner Starting")
	vbts.main()
