#!/usr/bin/python3
# VK Audio Player

import vlc, html, struct
from api import *
from Scurses import *
from utils import *; logstart('VKAudio')

db.setfile('VKAudio.db')
db.setbackup(False)
tokens.require('access_token', 'offline')

class VKAudioView(SCVSplitView):
	def __init__(self):
		super().__init__(-2)

	def init(self):
		super().init()
		self.p[0].addView(DialogsView())
		self.p[1].addView(ProgressView())

class DialogsView(SCSelectingListView):
	def __init__(self):
		super().__init__([{'name': '* My Audios', 'id': -1},
				  {'name': '* My Friends', 'id': -2},
				  {'name': '* Audio Search', 'id': -3}])
		self.toLoad = bool()
		self.loading = bool()

	def draw(self, stdscr):
		super().draw(stdscr)
		if (self.loading): self.loading = False; return
		if (isinstance(self.l[-1], dict) and not self.toLoad):
			stdscr.addstr(0, 0, 'Loading'.center(self.w), curses.A_STANDOUT) # FIXME not visible
			self.toLoad = True
			return
		if (self.toLoad):
			self.load()
			self.toLoad = False

	def key(self, c):
		if (c == curses.KEY_DOWN):
			self.n = min(self.n+1, len(self.l)-1-(self.l[-1] is None))
			self.scrollToSelected()
		elif (c == curses.KEY_NPAGE):
			self.n = min(self.n+self.h, len(self.l)-1-(self.l[-1] is None))
			self.scrollToSelected()
		elif (c == curses.KEY_END):
			self.n = len(self.l)-1-(self.l[-1] is None)
			self.scrollToSelected()
		else: return super().key(c)
		return True

	def item(self, i):
		text, attrs = super().item(i)
		if (self.l[i] is None): text = 'End.'
		elif (isinstance(self.l[i], int)): text = 'Loading...' if (self.loading) else 'Load more...'
		else: text = S(self.l[i]['name']).fit(self.w)
		return (text, attrs)

	def select(self):
		if (self.l[self.n] is None): self.n -= 1; return
		elif (isinstance(self.l[self.n], int)): self.loading = True; self.toLoad = True; return
		elif (self.l[self.n]['id'] == -1): self.app.w.addView(AudiosView(self.app.user_id))
		elif (self.l[self.n]['id'] == -2): self.app.w.addView(FriendsView())
		elif (self.l[self.n]['id'] == -3): self.app.w.addView(AudioSearchView())
		else: self.app.w.addView(AudiosView(self.l[self.n]['id'], im=True))

	def load(self):
		if (self.l[-1] is False): self.l[-1] = None; return
		if (not getvksid()): self.app.w.addView(LoginView()); return
		r = dialogs(count=self.h-1, start_message_id=self.l[-1] if (isinstance(self.l[-1], int)) else 0, extended=True, parse_attachments=False)
		if (len(self.l) > 3): self.l.pop()
		for i in r['items']:
			try:
				if (i['conversation']['peer']['type'] == 'user'): u = S(r['profiles'])['id', i['conversation']['peer']['id']][0]; self.l.append(S(u)&{'name': ' '.join(S(u)@['first_name', 'last_name'])})
				elif (i['conversation']['peer']['type'] == 'chat'): self.l.append({'name': i['conversation']['chat_settings']['title'], 'id': i['conversation']['peer']['id']})
				elif (i['conversation']['peer']['type'] == 'group'): self.l.append(S(r['groups'])['id', -i['conversation']['peer']['id']][0])
			except IndexError: pass
		self.l.append(r['has_more'] and i['conversation']['last_message_id'])

class FriendsView(SCSelectingListView):
	def __init__(self):
		super().__init__([])
		self.toLoad = bool()
		self.loading = bool()

	def draw(self, stdscr):
		super().draw(stdscr)
		if (self.loading): self.loading = False; return
		if (not self.l and not self.toLoad):
			stdscr.addstr(0, 0, 'Loading'.center(self.w), curses.A_STANDOUT)
			self.toLoad = True
			return
		if (self.toLoad):
			self.load()
			self.toLoad = False

	def key(self, c):
		if (c == curses.KEY_DOWN):
			self.n = min(self.n+1, len(self.l)-1-(self.l[-1] is None))
			self.scrollToSelected()
		elif (c == curses.KEY_NPAGE):
			self.n = min(self.n+self.h, len(self.l)-1-(self.l[-1] is None))
			self.scrollToSelected()
		elif (c == curses.KEY_END):
			self.n = len(self.l)-1-(self.l[-1] is None)
			self.scrollToSelected()
		else: return super().key(c)
		return True

	def item(self, i):
		text, attrs = super().item(i)
		if (self.l[i] is None): text = 'End.'
		elif (isinstance(self.l[i], int)): text = 'Loading...' if (self.loading) else 'Load more...'
		else: text = S(self.l[i]['name']).fit(self.w)
		return (text, attrs)

	def select(self):
		if (self.l[self.n] is None): self.n -= 1; return
		elif (isinstance(self.l[self.n], int)): self.loading = True; self.toLoad = True; return
		else: self.app.w.addView(AudiosView(self.l[self.n]['id']))

	def load(self):
		if (not getvksid()): self.app.w.addView(LoginView()); return
		r = API.audio.getFriends(exclude=S(',').join(S(self.l[:-1])@['id']))
		if (len(self.l)): self.l.pop()
		l = user(r)
		if (not l or l[0] in self.l): self.l.append(None); return
		self.l += l+[True]

class AudiosView(SCSelectingListView):
	def __init__(self, peer_id, search=None, im=False):
		super().__init__([int()])
		self.peer_id, self.search, self.im = peer_id, search, im
		self.toLoad = bool()
		self.toReselect = bool()
		self.loading = bool()

	def draw(self, stdscr):
		try: super().draw(stdscr) # FIXME crash
		except curses.error: return
		if (self.loading): self.loading = False; return
		if (self.l[0] is 0 and not self.toLoad):
			stdscr.addstr(0, 0, 'Loading'.center(self.w), curses.A_STANDOUT)
			self.toLoad = True
			self.toReselect = True
			return
		if (self.toLoad):
			self.load()
			self.toLoad = False
			if (self.toReselect): self.app.selectPlayingTrack(); self.toReselect = False

	def key(self, c):
		if (c == curses.KEY_DOWN):
			self.n = min(self.n+1, len(self.l)-1-(self.l[-1] is None))
			self.scrollToSelected()
		elif (c == curses.KEY_NPAGE):
			self.n = min(self.n+self.h, len(self.l)-1-(self.l[-1] is None))
			self.scrollToSelected()
		elif (c == curses.KEY_END):
			self.n = len(self.l)-1-(self.l[-1] is None)
			self.scrollToSelected()
		elif (c == 'n'):
			t = self.l[self.n]
			for ii, i in enumerate(self.app.play_next):
				if (isinstance(i, dict) and al_audio_eq(i, t)): del self.app.play_next[ii]; return
			else:
				self.app.playNext(t)
				self.app.setPlaylist(self.l, self.n, self.peer_id)
		elif (c == 'b'):
			self.app.selectPlayingTrack()
		else: return super().key(c)
		return True

	def item(self, i):
		text, attrs = super().item(i)
		if (self.l[i] is None): text = 'End.'
		elif (isinstance(self.l[i], int)): text = 'Loading...' if (self.loading) else 'Load more...'
		else:
			for jj, j in enumerate(self.app.play_next):
				if (al_audio_eq(j, self.l[i])): pn_pos = str(jj+1); break
			else: pn_pos = ''
			t_attrs = (pn_pos+' ' if (pn_pos) else '')+('HQ ' if (self.l[i]['is_hq']) else '')+self.app.strfTime(self.l[i]['duration'])
			text = S(f"{self.l[i]['artist']} — {self.l[i]['title']}").fit(self.w-len(t_attrs)-2)
			text += t_attrs.rjust(self.w-len(text))
		return (text, attrs)

	def select(self):
		if (self.l[self.n] is None): self.n -= 1; return
		elif (isinstance(self.l[self.n], int)): self.loading = True; self.toLoad = True; return
		self.app.setPlaylist(self.l, self.n, self.peer_id)
		self.app.playTrack()

	def load(self):
		if (self.l[-1] is False): self.l[-1] = None; return

		if (not getvksid()): self.app.w.addView(LoginView()); return
		if (self.search):
			r = API.audio.search(owner_id=self.peer_id, q=self.search, offset=self.l.pop())
			l = r['playlists'][1]['list']
		elif (not self.im): # TODO: playlists
			r = API.audio.get(owner_id=self.peer_id, offset=self.l.pop())
			l = r['list']
		else:
			r = API.messages.getHistoryAttachments(peer_id=self.peer_id, media_type='audio', count=self.h, start_from=self.l.pop())
			l = S(r['items'])@['attachment']@['audio']
		for i in l:
			if (self.l and self.l[-1] == i): continue
			self.l.append(i)
		self.l.append((r['has_more'] and r['next_from']) if (l) else None)

class AudioSearchView(SCView):
	def draw(self, stdscr):
		self.h, self.w = stdscr.getmaxyx()
		eh, ew = 5, 48
		ey, ex = (self.h-eh)//2, (self.w-ew)//2
		ep = curses.newwin(eh, ew, ey, ex)
		ep.addstr(0, 0, '╭'+'─'*(ew-2)+'╮')
		for i in range(1, eh-1): ep.addstr(i, 0, '│'+' '*(ew-2)+'│')
		ep.addstr(eh-2, 0, '╰'+'─'*(ew-2)+'╯')
		ep.addstr(1, 2, 'Audio Search'.center(ew-4))
		ep.addstr(2, 2, 'Query:')
		ep.refresh()
		y, x = stdscr.getbegyx()
		search = curses.textpad.Textbox(curses.newwin(y+1, x+ew-10, ey+2, ex+9))
		self.app.w.views.pop()
		self.app.w.addView(AudiosView(self.app.user_id, search=search.edit()))

class ProgressView(SCView):
	def draw(self, stdscr):
		super().draw(stdscr)
		pl = max(0, self.app.p.get_length())
		pp = min(1, self.app.p.get_position())
		pgrstr = f"{self.app.strfTime(pl*pp/1000)}/{self.app.strfTime(pl/1000)} %s {time.strftime('%X')}"
		stdscr.addstr(0, 1, S(app.trackline).fit(self.w-2-self.app.repeat*2).ljust(self.w-3)+' ↺'[self.app.repeat], curses.A_UNDERLINE)
		stdscr.addstr(1, 1, pgrstr % Progress.format_bar(pp, 1, self.w-len(pgrstr)))
		stdscr.addstr(1, 1, pgrstr.split('/')[0], curses.A_BLINK*(not self.app.p.is_playing()))
		if (self.app.p.get_state() == vlc.State.Ended): self.app.playNextTrack()

class LoginView(SCView):
	class PasswordBox(curses.textpad.Textbox):
		def __init__(self, *args, **kwargs):
			super().__init__(*args, **kwargs)
			self.result = str()

		def do_command(self, ch):
			if (ch in ('\b', curses.KEY_BACKSPACE)): self.result = self.result[:-1]
			return super().do_command(ch)

		def _insert_printable_char(self, ch):
			self.result += chr(ch)
			return super()._insert_printable_char('*')

		def gather(self):
			return self.result

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
		login, password = curses.textpad.Textbox(curses.newwin(y+1, x+ew-13, ey+2, ex+12)), self.PasswordBox(curses.newwin(y+1, x+ew-13, ey+3, ex+12))
		al_login(*map(str.strip, (login.edit(), password.edit())))
		self.app.w.views.pop()

class HelpView(SCView):
	def draw(self, stdscr):
		self.h, self.w = stdscr.getmaxyx()
		eh, ew = 16, 40
		ep = stdscr.subpad(eh, ew, (self.h-eh)//2, (self.w-ew)//2)
		ep.addstr(0, 0, '╭'+'─'*(ew-2)+'╮')
		for i in range(1, eh-1): ep.addstr(i, 0, '│'+' '*(ew-2)+'│')
		ep.addstr(eh-2, 0, '╰'+'─'*(ew-2)+'╯')
		for ii, i in enumerate('TODO:\n\nWrite help.'.split('\n')): ep.addstr(ii+1, 2, i) # TODO

	def key(self, c):
		self.app.w.views.pop()
		return True

class FindView(SCView):
	def __init__(self):
		self.q = '/'
		self.found = None

	def init(self):
		self.app.views[-1].focus = 1

	def draw(self, stdscr):
		self.app.views[-1].p[1].views[-2].draw(stdscr)
		self.h, self.w = stdscr.getmaxyx()
		with lc(''): stdscr.addstr(0, 0, self.q.encode(locale.getpreferredencoding()))

	def key(self, c):
		if (c == '\b' or c == curses.KEY_BACKSPACE):
			self.q = self.q[:-1]
			if (not self.q):
				self.cancel()
				self.app.waitkeyrelease(c)
		elif (c == '\n' or c == '\033' or c == curses.KEY_EXIT):
			self.cancel()
			if (c == '\n'): self.app.w.views[-1].key(c)
		elif (c.ch.isprintable()):
			self.q += c.ch
			for i in range(len(self.app.w.views[-1].l)):
				if (self.q[1:] in self.app.w.views[-1].item(i)[0]):
					self.app.w.views[-1].selectAndScroll(i)
					self.found = i
					break
			else: self.found = None
		return True

	def cancel(self):
		self.app.views[-1].focus = 0
		self.app.views[-1].p[1].views.pop()

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
		curses.curs_set(False)
		curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
		curses.mouseinterval(0)
		self.stdscr.nodelay(True)
		self.stdscr.leaveok(True)

		self.p = vlc.MediaPlayer()
		self.p.get_instance().log_unset()
		self.p.audio_set_volume(100)

		self.user_id = user()[0]['id']

		self.playlist = list()
		self.pl_pos = -1
		self.pl_peer = int()
		self.play_next = list()
		self.track = dict()
		self.error = bool()
		self.repeat = bool()
		self.clicked = bool()

		self.w = self.views[-1].p[0]

	@staticmethod
	def strfTime(t): return time.strftime('%H:%M:%S', time.gmtime(t)).lstrip('0').lstrip(':')

	def playTrack(self, t=None):
		if (t is None): return self.playTrack(self.playlist[self.pl_pos])
		self.error = False
		self.p.stop()
		try:
			al_audio_get_url(self.user_id, t) # in-place
			self.p.set_mrl(t['url'])
			self.p.play()
		except Exception: self.error = True; return False
		self.track = t
		self.selectPlayingTrack()
		return True

	def playNextTrack(self, force_next=False):
		if (self.repeat and not force_next): self.playTrack(self.track); return
		if (self.play_next): self.playTrack(self.play_next.pop(0)); return
		if (not self.playlist):
			if (not isinstance(self.w.views[-1], AudiosView)): return
			self.playlist = self.w.views[-1].l
		self.pl_pos = (self.pl_pos+1) % len(self.playlist)
		self.playTrack()

	def playPrevTrack(self):
		if (not self.playlist):
			if (not isinstance(self.w.views[-1], AudiosView)): return
			self.playlist = self.w.views[-1].l
		if (self.pl_pos): self.pl_pos -= 1
		self.playTrack()

	def selectPlayingTrack(self):
		if (not isinstance(self.w.views[-1], AudiosView) or self.w.views[-1].peer_id != self.pl_peer): return
		for ii, i in enumerate(self.w.views[-1].l):
			if (isinstance(i, dict) and al_audio_eq(i, self.track)): self.w.views[-1].selectAndScroll(ii); break

	def stop(self):
		self.p.stop()
		self.track = dict()
		self.w.views[-1].s = -1

	def setPlaylist(self, l, n=-1, peer_id=int()):
		self.playlist = l
		self.pl_pos = n
		self.pl_peer = peer_id

	def playNext(self, t):
		self.play_next.append(t)
		for ii, i in enumerate(self.playlist):
			if (isinstance(i, dict) and al_audio_eq(i, t)): self.pl_pos = ii; break

	def toggleRepeat(self):
		self.repeat = not self.repeat

	@property
	def trackline(self):
		return 'Error' if (self.error) else ('%(artist)s — %(title)s' % self.track) if (self.track) else ''

app = App()

@app.onkey('q')
@app.onkey('й') # same on cyrillic layout
@app.onkey('\033')
@app.onkey(curses.KEY_BACKSPACE)
@app.onkey(curses.KEY_EXIT)
def back(self, c):
	if (len(self.w.views) == 1): self.w.addView(QuitView()); return
	self.w.views.pop()

@app.onkey('h')
@app.onkey('р') # same on cyrillic layout
@app.onkey(curses.KEY_F1)
def help(self, c):
	self.w.addView(HelpView())

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
@app.onkey('з') # same on cyrillic layout
def pause(self, c):
	self.p.pause()

@app.onkey('a')
@app.onkey('ф') # same on cyrillic layout
def next(self, c):
	self.playNextTrack(force_next=True)

@app.onkey('z')
@app.onkey('я') # same on cyrillic layout
def prev(self, c):
	self.playPrevTrack()

@app.onkey('s')
@app.onkey('ы') # same on cyrillic layout
def stop(self, c):
	self.stop()
	self.setPlaylist([])

@app.onkey('r')
@app.onkey('к') # same on cyrillic layout
def repeat(self, c):
	self.toggleRepeat()

@app.onkey('/')
@app.onkey('.') # same on cyrillic layout
@app.onkey('^F')
@app.onkey(curses.KEY_FIND)
def find(self, c):
	self.views[-1].p[1].addView(FindView())

@app.onkey('^L')
def redraw(self, c):
	self.stdscr.redrawwin()

@app.onkey(curses.KEY_MOUSE)
def mouse(self, c):
	try: id, x, y, z, bstate = curses.getmouse()
	except (curses.error, IndexError): id = x = y = z = bstate = 0
	h, w = self.stdscr.getmaxyx()
	if (bstate == curses.BUTTON4_PRESSED): self.w.views[-1].t = max(self.w.views[-1].t-3, 0)
	elif (bstate == curses.REPORT_MOUSE_POSITION and len(self.w.views[-1].l) > h): self.w.views[-1].t = min(self.w.views[-1].t+3, len(self.w.views[-1].l)-h+2-(self.w.views[-1].l[-1] is None))
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
	app.addView(VKAudioView())
	app.run()

if (__name__ == '__main__'):
	logstarted()
	db.load()
	user()
	exit(main())
else: logimported()

# by Sdore, 2019
