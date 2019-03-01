#!/usr/bin/python3
# VK Audio Player

import vlc, html, vaud, struct
from api import *
from Scurses import *
from utils import *; logstart('VKAudio')

db.setfile('VKAudio.db')
db.setbackup(False)
tokens.require('access_token', 'messages,offline')

class Mouse:
	curses_map = {
		1: curses.BUTTON1_PRESSED,
		4: curses.BUTTON2_PRESSED,
		2: curses.BUTTON3_PRESSED,
	}

	def __init__(self, h, w):
		self.h, self.w = h, w
		self.fd = open('/dev/input/mice', 'rb')
		self.x = int()
		self.y = int()
	def getmouse(self):
		b, dx, mdy = struct.unpack('Bbb', select.select((self.fd,), (), (), 0)[0][0].read(3))
		self.x = Sint(self.x+dx).constrain(0, self.w-1)
		self.y = Sint(self.y-mdy/2).constrain(0, self.h-1)
		bstate = 0
		for i in self.curses_map:
			if (b & i): bstate |= self.curses_map[i]
		return (0, round(self.x), round(self.y), 0, bstate)

class DialogsView(SCSelectingListView):
	def __init__(self):
		super().__init__(list())
		self.toLoad = bool()

	def draw(self, stdscr):
		super().draw(stdscr)
		if (not self.l):
			stdscr.addstr(0, 0, 'Loading'.center(self.w), curses.A_STANDOUT)
			self.l.append({'name': '* My Audios', 'id': -1})
			self.toLoad = True
		if (self.toLoad):
			self.load()
			self.toLoad = False

	def key(self, c):
		if (c == curses.KEY_DOWN):
			self.n = min(self.n+1, len(self.l)-1-(not self.l[-1]))
			self.scrollToSelected()
		elif (c == curses.KEY_NPAGE):
			self.n = min(self.n+self.h, len(self.l)-1-(not self.l[-1]))
			self.scrollToSelected()
		elif (c == curses.KEY_END):
			self.n = len(self.l)-1-(not self.l[-1])
			self.scrollToSelected()
		else: return super().key(c)
		return True

	def item(self, i):
		text, attrs = super().item(i)
		if (self.l[i] == True): text = 'Load more...'
		elif (self.l[i] == False): text = 'End.'
		else: text = S(self.l[i]['name']).fit(self.w)
		return (text, attrs)

	def select(self):
		if (self.l[self.n] == False): self.n -= 1; return
		elif (self.l[self.n] == True): self.load(); return
		else: self.app.w.addView(AudiosView(self.l[self.n]['id']))

	def load(self):
		r = dialogs(count=self.h-1, offset=len(self.l), extended=1)
		if (len(self.l) > 1): self.l.pop()
		for i in r['items']:
			if (i['conversation']['peer']['type'] == 'user'): u = S(r['profiles'])['id', i['conversation']['peer']['id']][0]; self.l.append(S(u)&{'name': ' '.join(S(u)@['first_name', 'last_name'])})
			elif (i['conversation']['peer']['type'] == 'chat'): self.l.append({'name': i['conversation']['chat_settings']['title'], 'id': i['conversation']['peer']['id']})
			elif (i['conversation']['peer']['type'] == 'group'): self.l.append(S(r['groups'])['id', -i['conversation']['peer']['id']][0])
		self.l.append(bool(r['items']))

class AudiosView(SCSelectingListView):
	def __init__(self, peer_id):
		super().__init__([int()])
		self.peer_id = peer_id
		self.toLoad = bool()

	def draw(self, stdscr):
		super().draw(stdscr)
		if (len(self.l) <= 1):
			stdscr.addstr(0, 0, 'Loading'.center(self.w), curses.A_STANDOUT)
			self.toLoad = True
		if (self.toLoad):
			self.load()
			self.toLoad = False

	def key(self, c):
		if (c == curses.KEY_DOWN):
			self.n = min(self.n+1, len(self.l)-1-(not self.l[-1]))
			self.scrollToSelected()
		elif (c == curses.KEY_NPAGE):
			self.n = min(self.n+self.h, len(self.l)-1-(not self.l[-1]))
			self.scrollToSelected()
		elif (c == curses.KEY_END):
			self.n = len(self.l)-1-(not self.l[-1])
			self.scrollToSelected()
		else: return super().key(c)
		return True

	def item(self, i):
		text, attrs = super().item(i)
		if (type(self.l[i]) == str): text = 'Load more...'
		elif (not self.l[i]): text = 'End.'
		else:
			title_attrs = (str(self.app.play_next.index(i)+1)+' ' if (i in self.app.play_next) else '')+'HQ '*self.l[i]['is_hq']+self.app.strfTime(self.l[i]['duration'])
			title = S(f"{self.l[i]['artist']} — {self.l[i]['title']}").fit(self.w-len(title_attrs)-2)
			text = title+' '+title_attrs.rjust(self.w-len(title)-2)
		return (text, attrs)

	def select(self):
		if (self.l[self.n] is None): self.n -= 1; return
		elif (type(self.l[self.n]) == str): self.load(); return
		self.s = self.n
		self.app.p.stop()
		try:
			assert self.l[self.s]['url']
			self.app.p.set_mrl(self.l[self.s]['url'])
			self.app.p.play()
		except Exception: self.app.track = 'Error'
		else:
			self.app.track = '%(artist)s — %(title)s' % self.l[self.s]
			self.scrollToSelected()

	def load(self):
		if (self.peer_id == -1): # TODO: playlists, owners, FIXME missing urls
			if (not getvksid()): self.app.w.addView(LoginView()); return
			r = API.audio.get(owner_id=self.app.user_id, offset=self.l.pop())
			for i in r['list']: self.l.append({
				'title': html.unescape(i[3]),
				'artist': html.unescape(i[4]),
				'duration': i[5],
				'is_hq': False, # TODO ???
				'url': self.app.url_decoder.decode(i[2]),
			})#; log(i[2]) # FIXME
			self.l.append(str(r.get('nextOffset')) if (r['hasMore']) else None)
		else:
			r = API.messages.getHistoryAttachments(peer_id=self.peer_id, media_type='audio', count=self.h, start_from=self.l.pop())
			for i in S(r['items'])@['attachment']@['audio']:
				if (len(self.l) < 2 or self.l[-2] != i): self.l.append(i)
			self.l.append(r.get('next_from'))

class ProgressView(SCView):
	def draw(self, stdscr):
		super().draw(stdscr)
		pl = max(0, self.app.p.get_length())
		pp = min(1, self.app.p.get_position())
		pgrstr = f"{self.app.strfTime(pl*pp/1000)}/{self.app.strfTime(pl/1000)} %s {time.strftime('%X')}"
		stdscr.addstr(0, 1, S(app.track).fit(self.w-2-self.app.repeat*2).ljust(self.w-3)+' ↺'[self.app.repeat], curses.A_UNDERLINE)
		stdscr.addstr(1, 1, pgrstr % Progress.format_bar(pp, 1, self.w-len(pgrstr)))
		stdscr.addstr(1, 1, pgrstr.split('/')[0], curses.A_BLINK*(not self.app.p.is_playing()))
		if (self.app.p.get_state() == vlc.State.Ended): self.app.playNextTrack()

class LoginView(SCView): # TODO: hide password chars
	def draw(self, stdscr):
		self.h, self.w = stdscr.getmaxyx()
		eh, ew = 6, 48
		ey, ex = (self.h-eh)//2, (self.w-ew)//2
		ep = curses.newwin(eh, ew, ey, ex)
		ep.addstr(0, 0, '╭'+'─'*(ew-2)+'╮')
		for i in range(1, eh-1): ep.addstr(i, 0, '│'+' '*(ew-2)+'│')
		ep.addstr(eh-2, 0, '╰'+'─'*(ew-2)+'╯')
		ep.addstr(1, 2, 'Authorization'.center(ew-4))
		ep.addstr(2, 2, 'VK Login:')
		ep.addstr(3, 2, 'Password:')
		ep.refresh()
		y, x = stdscr.getbegyx()
		login, password = curses.textpad.Textbox(curses.newwin(y+1, x+ew-13, ey+2, ex+12)), curses.textpad.Textbox(curses.newwin(y+1, x+ew-13, ey+3, ex+12))
		al_login(*map(str.strip, (login.edit(), password.edit())))
		self.app.w.views.pop()

class QuitView(SCView):
	def draw(self, stdscr):
		self.h, self.w = stdscr.getmaxyx()
		eh, ew = 8, 23
		ep = stdscr.subpad(eh, ew, (self.h-eh)//2, (self.w-ew)//2)
		ep.addstr(0, 0, '╭'+'─'*(ew-2)+'╮')
		for i in range(1, eh-1): ep.addstr(i, 0, '│'+' '*(ew-2)+'│')
		ep.addstr(eh-2, 0, '╰'+'─'*(ew-2)+'╯')
		for ii, i in enumerate('Are you sure you\nwant to exit?\nPress the key again\nto exit or select\nto stay.'.split('\n')): ep.addstr(1+ii, 2, i.center(ew-3), curses.A_BOLD)

	def key(self, c):
		if (c == '\n'): self.app.w.views.pop()
		elif (c == 'q' or c == '\033' or c == curses.KEY_BACKSPACE or c == curses.KEY_EXIT): self.app.views.pop()
		else: return super().key(c)
		return True

class App(SCApp):
	def init(self):
		super().init()
		curses.use_default_colors()
		curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
		curses.mouseinterval(0)
		self.stdscr.nodelay(True)

		if (os.environ['TERM'] == 'linux'): self.mouse = None#Mouse(*stdscr.getmaxyx())
		else: self.mouse = None
		curses.curs_set(2*bool(self.mouse))
		self.stdscr.leaveok(not self.mouse)

		self.p = vlc.MediaPlayer()
		self.p.get_instance().log_unset()
		self.p.audio_set_volume(100)

		self.user_id = user()[0]['id']
		self.url_decoder = vaud.Decoder(self.user_id)

		self.track = str()
		self.repeat = bool()
		self.play_next = list()
		self.clicked = bool()

		self.views[-1].p[0].addView(DialogsView())
		self.views[-1].p[1].addView(ProgressView())
		self.w = self.views[-1].p[0]

	@staticmethod
	def strfTime(t): return time.strftime('%H:%M:%S', time.gmtime(t)).lstrip('0').lstrip(':')

	def playNextTrack(self, force_next=False):
		if (self.play_next): self.w.views[-1].n = self.play_next.pop(0)
		elif (not self.repeat or force_next): self.w.views[-1].n = (self.w.views[-1].s+1) % len(self.w.views[-1].l)
		self.w.views[-1].select()

	def playPrevTrack(self, ):
		self.w.views[-1].n = max(self.w.views[-1].n-1, 0)
		self.w.views[-1].select()

	def toggleRepeat(self):
		self.repeat = not self.repeat

app = App()

@app.onkey('q')
@app.onkey('\033')
@app.onkey(curses.KEY_BACKSPACE)
@app.onkey(curses.KEY_EXIT)
def back(self, c):
	if (len(self.w.views) == 1): self.w.addView(QuitView()); return
	self.w.views.pop()

@app.onkey(curses.KEY_LEFT)
def rew(self, c):
	self.p.set_position(self.p.get_position()-0.01)
@app.onkey(curses.KEY_RIGHT)
def fwd(self, c):
	self.p.set_position(self.p.get_position()+0.01)

@app.onkey('1')
@app.onkey('2')
@app.onkey('3')
@app.onkey('4')
@app.onkey('5')
@app.onkey('6')
@app.onkey('7')
@app.onkey('8')
@app.onkey('9')
@app.onkey('0')
def seek(self, c):
	if (self.p.is_playing()): self.p.set_position(0.1*('1234567890'.index(c.ch)))

@app.onkey(' ')
@app.onkey('p')
def pause(self, c):
	self.p.pause()

@app.onkey('a')
def next(self, c):
	self.playNextTrack(force_next=True)

@app.onkey('z')
def prev(self, c):
	self.playPrevTrack()

@app.onkey('s')
def stop(self, c):
	self.p.stop()
	self.w.views[-1].s = -1

@app.onkey('r')
def repeat(self, c):
	self.toggleRepeat()

@app.onkey('n')
def pnext(self, c):
	if (self.w.views[-1].n in self.play_next): self.play_next.remove(self.w.views[-1].n)
	else: self.play_next.append(self.w.views[-1].n)

@app.onkey('b')
def stsel(self, c):
	if (self.w.views[-1].s != -1): self.w.views[-1].n = self.w.views[-1].s
	self.w.views[-1].scrollToSelected()

@app.onkey(curses.KEY_MOUSE)
def mouse(self, c):
	try: id, x, y, z, bstate = (self.mouse or curses).getmouse()
	except (curses.error, IndexError): id = x = y = z = bstate = 0
	if (self.mouse): stdscr.move(y, x)
	h, w = self.stdscr.getmaxyx()
	if (bstate == curses.BUTTON4_PRESSED): self.w.views[-1].t = max(self.w.views[-1].t-3, 0)
	elif (bstate == curses.REPORT_MOUSE_POSITION and len(self.w.views[-1].l) > h): self.w.views[-1].t = min(self.w.views[-1].t+3, len(self.w.views[-1].l)-h)
	else:
		if (y < h-2):
			if (bstate == curses.BUTTON1_PRESSED):
				if (isinstance(self.w.views[-1], QuitView)): self.w.views.pop(); return
				self.w.views[-1].n = self.w.views[-1].t+y
				if (time.time() < self.clicked): self.w.views[-1].select(); self.clicked = True
			elif (bstate == curses.BUTTON1_RELEASED): self.clicked = False if (self.clicked == True) else time.time()+0.2
			elif (bstate == curses.BUTTON3_PRESSED):
				if (isinstance(self.w.views[-1], QuitView)): self.views.pop(); return
				back(self, c)
		elif (y == h-2 and x >= w-2):
			if (bstate == curses.BUTTON1_PRESSED): self.toggleRepeat()
		elif (y == h-1 and 14 <= x <= w-12):
			if (bstate == curses.BUTTON1_PRESSED or bstate == curses.REPORT_MOUSE_POSITION):
				if (self.p.is_playing()): self.p.set_position((x-14)/(w-12-14+1))

def main():
	app.addView(SCVSplitView(-2))
	app.run()

if (__name__ == '__main__'):
	logstarted()
	db.load()
	user()
	exit(main())
else: logimported()

# by Sdore, 2019
