#!/usr/bin/python3
# VK Audio Player

import gi, vlc, html, struct
from api import *
from Scurses import *
from utils import *; logstart('VKAudio')
try: gi.require_version('Notify', '0.7')
except ValueError: pass
else: from gi.repository import GLib, Notify

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

class DialogsView(SCLoadingSelectingListView):
	def __init__(self):
		super().__init__([{'name': '* My Audios', 'id': -1},
				  {'name': '* My Friends', 'id': -2},
				  {'name': '* Audio Search', 'id': -3}])
		self.toLoad = True
		self.loading = True

	def item(self, i):
		ret, text, attrs = super().item(i)
		if (not ret):
			text = S(self.l[i]['name']).fit(self.w)
		return (ret, text, attrs)

	def select(self):
		if (super().select()): return True
		elif (self.l[self.n]['id'] == -1): self.app.w.addView(AudiosView(self.app.user_id))
		elif (self.l[self.n]['id'] == -2): self.app.w.addView(FriendsView())
		elif (self.l[self.n]['id'] == -3): self.app.w.addView(AudioSearchView())
		else: self.app.w.addView(AudiosView(self.l[self.n]['id'], im=True))

	def load(self):
		ret = super().load()
		if (not ret):
			if (not getvksid()): self.app.w.addView(LoginView()); return
			r = dialogs(count=self.h-1, start_message_id=(self.l[-1].next_value or 0), extended=True, parse_attachments=False)
			if (len(self.l) > 3): self.l.pop()
			for i in r['items']:
				try:
					if (i['conversation']['peer']['type'] == 'user'): u = S(r['profiles'])['id', i['conversation']['peer']['id']][0]; self.l.append(S(u)&{'name': ' '.join(S(u)@['first_name', 'last_name'])})
					elif (i['conversation']['peer']['type'] == 'chat'): self.l.append({'name': i['conversation']['chat_settings']['title'], 'id': i['conversation']['peer']['id']})
					elif (i['conversation']['peer']['type'] == 'group'): self.l.append(S(r['groups'])['id', -i['conversation']['peer']['id']][0])
				except IndexError: pass
			self.l.append(self.LoadItem(r['has_more'], i['conversation']['last_message_id']))
		return ret

class FriendsView(SCLoadingSelectingListView):
	def __init__(self):
		super().__init__([])
		self.toLoad = True
		self.loading = True

	def item(self, i):
		ret, text, attrs = super().item(i)
		if (not ret):
			text = S(self.l[i]['name']).fit(self.w)
		return (ret, text, attrs)

	def select(self):
		ret = super().select()
		if (not ret):
			self.app.w.addView(AudiosView(self.l[self.n]['id']))
		return ret

	def load(self):
		ret = super().load()
		if (not ret):
			if (not getvksid()): self.app.w.addView(LoginView()); return
			r = API.audio.getFriends(exclude=S(',').join(S(self.l[:-1])@['id']))
			if (len(self.l)): self.l.pop()
			l = user(r)
			if (not l or l[0] in self.l): self.l.append(self.LoadItem(False)); return
			self.l += l
			self.l.append(self.LoadItem())
		return ret

class AudiosView(SCLoadingSelectingListView):
	def __init__(self, peer_id, search=None, im=False):
		super().__init__([])
		self.peer_id, self.search, self.im = peer_id, search, im
		self.toReselect = bool()
		self.toLoad = True
		self.loading = True

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
		if (c == 'n' or c == 'т'):
			t = self.l[self.n]
			for ii, i in enumerate(self.app.play_next):
				if (isinstance(i, dict) and al_audio_eq(i, t)): del self.app.play_next[ii]; return
			else:
				self.app.playNext(t)
				self.app.setPlaylist(self.l, self.n, self.peer_id)
		elif (c == 'k' or c == 'л'):
			self.selectAndScroll(random.randrange(len(self.l)))
		elif (c == 'b' or c == 'и'):
			self.app.selectPlayingTrack()
		elif (c == 'd' or c == 'в'):
			curses.def_prog_mode()
			curses.endwin()
			os.system(f"""wget "{al_audio_get_url(self.app.user_id, self.l[self.n])}" -O "{'%(artist)s - %(title)s.mp3' % self.l[self.n]}" -q --show-progress""")
			curses.reset_prog_mode()
		else: return super().key(c)
		return True

	def item(self, i):
		ret, text, attrs = super().item(i)
		if (not ret):
			for jj, j in enumerate(self.app.play_next):
				if (al_audio_eq(j, self.l[i])): pn_pos = str(jj+1); break
			else: pn_pos = ''
			t_attrs = (pn_pos+' ' if (pn_pos) else '')+('HQ ' if (self.l[i]['is_hq']) else '')+self.app.strfTime(self.l[i]['duration'])
			text = S('%(artist)s — %(title)s' % self.l[i]).fit(self.w-len(t_attrs)-1)
			text += t_attrs.rjust(self.w-len(text))
		return (ret, text, attrs)

	def select(self):
		ret = super().select()
		if (not ret):
			self.app.setPlaylist(self.l, self.n, self.peer_id)
			self.app.playTrack()
		return ret

	def load(self):
		ret = super().load()
		if (not ret):
			if (not getvksid()): self.app.w.addView(LoginView()); return
			if (self.search):
				r = API.audio.search(owner_id=self.peer_id, q=self.search, offset=self.l.pop().next_value)
				l = r['playlists'][1]['list'] if (len(r['playlists']) > 1) else []
			elif (not self.im): # TODO: playlists
				r = API.audio.get(owner_id=self.peer_id, offset=self.l.pop().next_value)
				l = r['list']
			else:
				r = API.messages.getHistoryAttachments(peer_id=self.peer_id, media_type='audio', count=self.h, start_from=self.l.pop().next_value)
				l = S(r['items'])@['attachment']@['audio']
			for i in l:
				if (self.l and self.l[-1] == i): continue
				self.l.append(i)
			self.l.append(SCLoadingListView.LoadItem(bool(l) and r.get('has_more'), r.get('next_from')))
		return ret

class AudioSearchView(SCView): # TODO FIXME: unicode input
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
		if (pl and self.app.p.get_state() == vlc.State.Ended): self.app.playNextTrack()

class LoginView(SCView):
	class PasswordBox(curses.textpad.Textbox):
		def __init__(self, *args, **kwargs):
			super().__init__(*args, **kwargs)
			self.result = str()

		def do_command(self, ch):
			if (ch in ('\b', '\x7f', curses.KEY_BACKSPACE)): self.result = self.result[:-1]
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
		eh, ew = 18, 40
		ep = stdscr.subpad(eh, ew, (self.h-eh)//2, (self.w-ew)//2)
		ep.addstr(0, 0, '╭'+'─'*(ew-2)+'╮')
		for i in range(1, eh-1): ep.addstr(i, 0, '│'+' '*(ew-2)+'│')
		ep.addstr(eh-2, 0, '╰'+'─'*(ew-2)+'╯')
		for ii, i in enumerate("""\
           VKAudio: Help
q, esc, bspace — back
r — toggle repeat
p — toggle pause
a — next track
s — stop
d — download track using wget
h — help
k — select random track
z — previous track
b — select playing track
n — enqueue track
left/right, nums — seek
/, ^F — find
^L — force redraw""".split('\n')): ep.addstr(ii+1, 2, i)

	def key(self, c):
		self.app.w.views.pop()
		return True

class FindView(SCView): # TODO: more intuitive control?
	def __init__(self):
		self.q = '/'
		self.found = None

	def init(self):
		self.app.top.focus = 1

	def draw(self, stdscr):
		self.app.top.p[1].views[-2].draw(stdscr)
		self.h, self.w = stdscr.getmaxyx()
		with lc(''): stdscr.addstr(0, 0, self.q.encode(locale.getpreferredencoding()))

	def key(self, c):
		if (c == '\b' or c == '\x7f' or c == curses.KEY_BACKSPACE):
			self.q = self.q[:-1]
			if (not self.q):
				self.cancel()
				self.app.waitkeyrelease(c)
		elif (c == '\n' or c == '\033' or c == curses.KEY_EXIT):
			self.cancel()
			if (c == '\n'): self.app.w.top.key(c)
		elif (c.ch.isprintable()):
			self.q += c.ch
			for i in range(self.app.w.top.n, len(self.app.w.top.l)):
				if (self.q[1:].casefold() in self.app.w.top.item(i)[1].casefold()):
					self.app.w.top.selectAndScroll(i)
					self.found = i
					break
			else: self.found = None
		return True

	def cancel(self):
		self.app.top.focus = 0
		self.app.top.p[1].views.pop()

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
		elif (c == 'q' or c == 'й' or c == '\b' or c == '\x7f' or c == '\033' or c == curses.KEY_BACKSPACE or c == curses.KEY_EXIT): self.app.views.pop()
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

		try: self.eventloop = GLib.MainLoop()
		except NameError: self.eventloop = None
		else:
			self.eventloopthread = threading.Thread(target=self.eventloop.run, daemon=True)
			self.eventloopthread.start()

		try: Notify.init('VKAudio')
		except Exception as ex: self.notify = None
		else:
			self.notify = Notify.Notification.new('')
			self.notify.set_category('x-gnome.music')
			self.notify.set_urgency(Notify.Urgency.LOW)
			self.notify.set_hint('action-icons', GLib.Variant('b', True))
			self.notify.add_action('media-skip-backward', 'Previous track', lambda *args: self.playPrevTrack())
			self.notify.add_action('media-playback-pause', 'Pause', lambda *args: self.playPause())
			self.notify.add_action('media-skip-forward', 'Next track', lambda *args: self.playNextTrack())

		self.user_id = user()[0]['id']

		self.playlist = list()
		self.pl_pos = -1
		self.pl_peer = int()
		self.play_next = list()
		self.track = dict()
		self.error = None
		self.repeat = bool()
		self.clicked = bool()

		self.w = self.top.p[0]

	@staticmethod
	def strfTime(t): return time.strftime('%H:%M:%S', time.gmtime(t)).lstrip('0').lstrip(':')

	def playTrack(self, t=None):
		if (t is None): return self.playTrack(self.playlist[self.pl_pos])
		self.error = None
		self.p.stop()
		try:
			al_audio_get_url(self.user_id, t) # in-place
			self.p.set_mrl(t['url'])
			self.p.play()
		except Exception as ex: self.error = ex; return False
		self.notifyPlaying(t)
		self.track = t
		self.selectPlayingTrack()
		return True

	def playNextTrack(self, force_next=False):
		if (self.repeat and not force_next): self.playTrack(self.track); return
		if (self.play_next): self.playTrack(self.play_next.pop(0)); return
		if (not self.playlist):
			if (not isinstance(self.w.top, AudiosView)): return
			self.playlist = self.w.top.l
			self.pl_peer = self.w.top.peer_id
		self.pl_pos = (self.pl_pos+1) % len(self.playlist)
		self.playTrack()

	def playPrevTrack(self):
		if (not self.playlist):
			if (not isinstance(self.w.top, AudiosView)): return
			self.playlist = self.w.top.l
		if (self.pl_pos): self.pl_pos -= 1
		self.playTrack()

	def selectPlayingTrack(self):
		if (not isinstance(self.w.top, AudiosView) or self.w.top.peer_id != self.pl_peer): return
		for ii, i in enumerate(self.w.top.l):
			if (isinstance(i, dict) and al_audio_eq(i, self.track)): self.w.top.selectAndScroll(ii); break

	def playPause(self):
		self.p.pause()

	def stop(self):
		self.p.stop()
		self.track = dict()
		self.w.top.s = -1

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

	def seekRew(self):
		self.p.set_position(self.p.get_position()-0.01)

	def seekFwd(self):
		self.p.set_position(self.p.get_position()+0.01)

	def notifyPlaying(self, t):
		try:
			self.notify.update(t['title'], t['artist'])
			self.notify.show()
		except Exception: pass

	@property
	def trackline(self):
		return 'Error: '+str(self.error) if (self.error is not None) else ('%(artist)s — %(title)s' % self.track) if (self.track) else ''

app = App()

@app.onkey('q')
@app.onkey('й')
@app.onkey('\b')
@app.onkey('\x7f')
@app.onkey('\033')
@app.onkey(curses.KEY_BACKSPACE)
@app.onkey(curses.KEY_EXIT)
def back(self, c):
	if (len(self.w.views) == 1): self.w.addView(QuitView()); return
	self.w.views.pop()

@app.onkey('h')
@app.onkey('р')
@app.onkey(curses.KEY_F1)
def help(self, c):
	self.w.addView(HelpView())

@app.onkey(curses.KEY_LEFT)
def rew(self, c):
	self.seekRew()
@app.onkey(curses.KEY_RIGHT)
def fwd(self, c):
	self.seekFwd()

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
@app.onkey('з')
def pause(self, c):
	self.playPause()

@app.onkey('a')
@app.onkey('ф')
def next(self, c):
	self.playNextTrack(force_next=True)

@app.onkey('z')
@app.onkey('я')
def prev(self, c):
	self.playPrevTrack()

@app.onkey('s')
@app.onkey('ы')
def stop(self, c):
	self.stop()
	self.setPlaylist([])

@app.onkey('r')
@app.onkey('к')
def repeat(self, c):
	self.toggleRepeat()

@app.onkey('/')
@app.onkey('.')
@app.onkey('^F')
@app.onkey(curses.KEY_FIND)
def find(self, c):
	self.top.p[1].addView(FindView())

@app.onkey('^L')
def redraw(self, c):
	self.stdscr.redrawwin()

@app.onkey(curses.KEY_MOUSE)
def mouse(self, c):
	try: id, x, y, z, bstate = curses.getmouse()
	except (curses.error, IndexError): id = x = y = z = bstate = 0
	h, w = self.stdscr.getmaxyx()
	if (y < h-2):
		if (bstate == curses.BUTTON4_PRESSED): self.w.top.t = max(self.w.top.t-3, 0)
		elif (bstate == curses.REPORT_MOUSE_POSITION or bstate == 2097152 and len(self.w.top.l) > h): self.w.top.t = min(self.w.top.t+3, len(self.w.top.l)-h+2-(self.w.top.l[-1] is None))
		elif (bstate == curses.BUTTON1_PRESSED):
			if (isinstance(self.w.top, QuitView)): self.w.views.pop(); return
			self.w.top.n = self.w.top.t+y
			if (time.time() < self.clicked): self.w.top.select(); self.clicked = True
		elif (bstate == curses.BUTTON1_RELEASED):
			self.clicked = False if (self.clicked == True) else time.time()+0.2
		elif (bstate == curses.BUTTON3_PRESSED):
			if (isinstance(self.w.top, QuitView)): self.views.pop(); return
			back(self, c)
	elif (y == h-2 and x >= w-2):
		if (bstate == curses.BUTTON1_PRESSED): self.toggleRepeat()
	elif (y == h-1):
		if (x < 14):
			if (bstate in (curses.BUTTON1_PRESSED, curses.BUTTON3_PRESSED, curses.BUTTON3_RELEASED)):
				self.p.pause()
		elif (x <= w-12 and self.p.is_playing()):
			if (bstate == curses.BUTTON1_PRESSED):
				self.p.set_position((x-14)/(w-12-14+1))
			elif (bstate == curses.BUTTON4_PRESSED):
				self.seekRew()
			elif (bstate == curses.REPORT_MOUSE_POSITION or bstate == 2097152):
				self.seekFwd()

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
