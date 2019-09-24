#!/usr/bin/python3
# VK Audio Player

import vlc, html, struct, notify2, dbus.service, dbus.mainloop.glib
from api import *
from Scurses import *
from utils import *; logstart('VKAudio')
from gi.repository import GLib

db.setfile('VKAudio.db')
db.setbackup(False)
tokens.require('access_token', 'offline')

class MediaPlayer2(dbus.service.Object):
	def __init__(self, app, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.app = app

	@dbus.service.method('org.mpris.MediaPlayer2.Player')
	def PlayPause(self):
		self.app.playPause()

	@dbus.service.method('org.mpris.MediaPlayer2.Player')
	def Previous(self):
		self.app.playPrevTrack()

	@dbus.service.method('org.mpris.MediaPlayer2.Player')
	def Next(self):
		self.app.playNextTrack()

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
				  {'name': '* My Albums', 'id': -2},
				  {'name': '* My Friends', 'id': -3},
				  {'name': '* Audio Search', 'id': -4}])
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
		elif (self.l[self.n]['id'] == -2): self.app.w.addView(AlbumsView())
		elif (self.l[self.n]['id'] == -3): self.app.w.addView(FriendsView())
		elif (self.l[self.n]['id'] == -4): self.app.w.addView(AudioSearchView())
		else: self.app.w.addView(AudiosView(self.l[self.n]['id'], im=True))

	def load(self):
		ret = super().load()
		if (not ret):
			try: r = dialogs(count=self.h-1, start_message_id=(self.l[-1].next_value or None), extended=True, parse_attachments=False)
			except VKAlLoginError: self.app.w.addView(LoginView()); return
			if (len(self.l) > 3): self.l.pop()
			for i in r['items']:
				try:
					if (i['conversation']['peer']['type'] == 'user'): u = S(r['profiles'])['id', i['conversation']['peer']['id']][0]; self.l.append(S(u)&{'name': ' '.join(S(u)@['first_name', 'last_name'])})
					elif (i['conversation']['peer']['type'] == 'chat'): self.l.append({'name': i['conversation']['chat_settings']['title'], 'id': i['conversation']['peer']['id']})
					elif (i['conversation']['peer']['type'] == 'group'): self.l.append(S(r['groups'])['id', -i['conversation']['peer']['id']][0])
				except IndexError: pass
			self.l.append(self.LoadItem(r.get('has_more', bool(r)), i['conversation']['last_message_id']-1))
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
			try: r = API.audio.getFriends(exclude=S(',').join(S(self.l[:-1])@['id']))
			except VKAlLoginError: self.app.w.addView(LoginView()); return
			if (self.l): self.l.pop()
			l = user(r)
			if (not l or l[0] in self.l): self.l.append(self.LoadItem(False)); return
			self.l += l
			self.l.append(self.LoadItem())
		return ret

class AlbumsView(SCLoadingSelectingListView):
	def __init__(self):
		super().__init__([])
		self.toLoad = True
		self.loading = True

	def item(self, i):
		ret, text, attrs = super().item(i)
		if (not ret):
			text = S(self.l[i]['title']).fit(self.w)
		return (ret, text, attrs)

	def select(self):
		ret = super().select()
		if (not ret):
			self.app.w.addView(AudiosView(self.l[self.n]['owner_id'], album_id=self.l[self.n]['id'], access_hash=self.l[self.n]['access_hash']))
		return ret

	def load(self):
		ret = super().load()
		if (not ret):
			try: r = API.audio.getAlbums(owner_id=self.app.user_id)
			except VKAlLoginError: self.app.w.addView(LoginView()); return
			if (self.l): self.l.pop()
			self.l += r['items']
			self.l.append(self.LoadItem(False)) # TODO FIXME
		return ret

class AudiosView(SCLoadingSelectingListView):
	def __init__(self, peer_id, album_id=-1, access_hash=None, search=None, im=False):
		super().__init__([])
		self.peer_id, self.album_id, self.access_hash, self.search, self.im = peer_id, album_id, access_hash, search, im
		self.toLoad = True
		self.loading = True
		self.toReselect = True

	def draw(self, stdscr):
		try: super().draw(stdscr) # FIXME crash?
		except curses.error: pass
		if (self.toReselect and not isinstance(self.l[0], SCLoadingListView.LoadItem)):
			self.app.selectPlayingTrack()
			self.toReselect = False

	def key(self, c):
		if (c == 'n' or c == 'т'):
			t = self.l[self.n]
			for ii, i in enumerate(self.app.play_next):
				if (isinstance(i, dict) and al_audio_eq(i, t)): del self.app.play_next[ii]; return
			else:
				self.app.playNext(t)
				self.app.setPlaylist(self.l, self.n, self.peer_id)
		elif (c == 'k' or c == 'л'):
			self.selectAndScroll(random.randrange(len(self.l)-1))
		elif (c == 'b' or c == 'и'):
			self.app.selectPlayingTrack()
		elif (c == 'd' or c == 'в'):
			curses.def_prog_mode()
			curses.endwin()
			os.system(f"""wget "{al_audio_get_url(self.app.user_id, self.l[self.n])}" -O "{'%(artist)s - %(title)s.mp3' % self.l[self.n]}" -q --show-progress""")
			curses.reset_prog_mode()
		elif (c == 'l' or c == 'д'):
			self.app.w.addView(LyricsView(self.l[self.n]['lyrics_id']))
		else: return super().key(c)
		return True

	def item(self, i):
		ret, text, attrs = super().item(i)
		if (not ret):
			for jj, j in enumerate(self.app.play_next):
				if (al_audio_eq(j, self.l[i])): pn_pos = str(jj+1); break
			else: pn_pos = ''
			t_attrs = (pn_pos+' ' if (pn_pos) else '')+('HQ ' if (self.l[i].get('is_hq')) else '')+self.app.strfTime(self.l[i]['duration'])
			text = S('%(artist)s — %(title)s' % self.l[i]).fit(self.w-len(t_attrs)-1)
			text += t_attrs.rjust(self.w-len(text))
		return (ret, text, attrs)

	def select(self):
		ret = super().select()
		if (not ret):
			self.app.setPlaylist(self.l, self.n, self.peer_id)
			self.app.playTrack()
		return ret

	# TODO: somehow prettify following:

	@staticmethod
	@cachedfunction
	def _search(*args, **kwargs):
		return API.audio.search(*args, **kwargs)

	@staticmethod
	@cachedfunction
	def _get(*args, **kwargs):
		return API.audio.get(*args, **kwargs)

	@staticmethod
	@cachedfunction
	def _history(*args, **kwargs):
		return API.messages.getHistoryAttachments(*args, **kwargs)

	def load(self):
		ret = super().load()
		if (not ret):
			try:
				if (self.search):
					r = self._search(owner_id=self.peer_id, q=self.search, offset=self.l.pop().next_value)
					l = r['playlists'][-1]['list'] if (r['playlists']) else []
				elif (not self.im):
					r = self._get(owner_id=self.peer_id, album_id=self.album_id, access_hash=self.access_hash, offset=self.l.pop().next_value)
					l = r['list']
				else:
					r = self._history(peer_id=self.peer_id, media_type='audio', count=self.h, start_from=self.l.pop().next_value)
					l = S(r['items'])@['attachment']@['audio']
			except VKAlLoginError: self.app.w.addView(LoginView()); return
			for i in l:
				if (self.l and self.l[-1] == i): continue
				self.l.append(i)
			self.l.append(SCLoadingListView.LoadItem(r.get('has_more', bool(l)), r.get('next_from')))
		return ret

class PlaylistView(AudiosView): # TODO
	pass

class LyricsView(SCView):
	eh, ew = 18, 75

	def __init__(self, lyrics_id):
		super().__init__()
		self.lyrics_id = lyrics_id
		self.text = str()
		self.offset = int()

	def init(self):
		self.text = S(API.audio.getLyrics(lyrics_id=self.lyrics_id)['text']).wrap(self.ew-3)

	def draw(self, stdscr):
		self.h, self.w = stdscr.getmaxyx()
		ep = stdscr.subpad(self.eh, self.ew, (self.h-self.eh)//2, (self.w-self.ew)//2)
		ep.addstr(0, 0, '╭'+'─'*(self.ew-2)+'╮')
		for i in range(1, self.eh-1): ep.addstr(i, 0, '│'+' '*(self.ew-2)+'│')
		ep.addstr(self.eh-2, 0, '╰'+'─'*(self.ew-2)+'╯')
		for ii, i in enumerate(self.text.split('\n')[self.offset:self.eh-3+self.offset]): ep.addstr(ii+1, 2, i)

	def key(self, c):
		if (c == curses.KEY_UP):
			self.offset = max(0, self.offset-1)
		elif (c == curses.KEY_DOWN):
			self.offset = min(self.offset+1, self.text.count('\n')-self.eh+4)
		else: return super().key(c)
		return True

class AudioSearchView(SCView):
	class SearchBox(curses.textpad.Textbox):
		def __init__(self, *args, **kwargs):
			super().__init__(*args, **kwargs)
			self.result = str()

		def _insert_printable_char(self, ch):
			self.result += ch.ch
			self._update_max_yx()
			y, x = self.win.getyx()
			backyx = None
			while (y < self.maxy or x < self.maxx):
				if (self.insert_mode): oldch = SCKey(self.win.inch())
				try: self.win.addch(ch.ch)
				except curses.error: pass
				if (not self.insert_mode or not oldch.ch.isprintable()): break
				ch = oldch
				y, x = self.win.getyx()
				if (backyx is None): backyx = y, x
			if (backyx is not None): self.win.move(*backyx)

		def do_command(self, ch):
			ch = SCKey(ch)
			self._update_max_yx()
			y, x = self.win.getyx()
			self.lastcmd = ch
			if (ch.ch.isprintable()):
				if (y < self.maxy or x < self.maxx): self._insert_printable_char(ch)
			elif (ch == curses.ascii.SOH): # ^A
				self.win.move(y, 0)
			elif (ch in (curses.ascii.STX, curses.KEY_LEFT, curses.ascii.BS, curses.ascii.DEL, curses.KEY_BACKSPACE)):
				self.result = self.result[:-1]
				if (x > 0): self.win.move(y, x-1)
				elif (y == 0): pass
				elif (self.stripspaces): self.win.move(y-1, self._end_of_line(y-1))
				else: self.win.move(y-1, self.maxx)
				if (ch in (curses.ascii.BS, curses.ascii.DEL, curses.KEY_BACKSPACE)): self.win.delch()
			elif (ch == curses.ascii.EOT): # ^D
				self.win.delch()
			elif (ch == curses.ascii.ENQ): # ^E
				if (self.stripspaces): self.win.move(y, self._end_of_line(y))
				else: self.win.move(y, self.maxx)
			elif (ch in (curses.ascii.ACK, curses.KEY_RIGHT)): # ^F
				if (x < self.maxx): self.win.move(y, x+1)
				elif (y == self.maxy): pass
				else: self.win.move(y+1, 0)
			elif (ch == curses.ascii.BEL): # ^G
				return 0
			elif (ch == curses.ascii.NL): # ^J
				if (self.maxy == 0): return 0
				elif (y < self.maxy): self.win.move(y+1, 0)
			elif (ch == curses.ascii.VT): # ^K
				if (x == 0 and self._end_of_line(y) == 0): self.win.deleteln()
				else:
					self.win.move(y, x)
					self.win.clrtoeol()
			elif (ch == curses.ascii.FF): # ^L
				self.win.refresh()
			elif (ch in (curses.ascii.SO, curses.KEY_DOWN)): # ^N
				if (y < self.maxy):
					self.win.move(y+1, x)
					if (x > self._end_of_line(y+1)): self.win.move(y+1, self._end_of_line(y+1))
			elif (ch == curses.ascii.SI): # ^O
				self.win.insertln()
			elif (ch in (curses.ascii.DLE, curses.KEY_UP)): # ^P
				if (y > 0):
					self.win.move(y-1, x)
					if (x > self._end_of_line(y-1)): self.win.move(y-1, self._end_of_line(y-1))
			return 1

		def edit(self, validate=None):
			while (True):
				ch = self.win.get_wch()
				if (validate): ch = validate(ch)
				if (not ch): continue
				if (not self.do_command(ch)): break
				self.win.refresh()
			return self.result

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
		search = self.SearchBox(curses.newwin(y+1, x+ew-10, ey+2, ex+9))
		self.app.w.views.pop()
		self.app.w.addView(AudiosView(self.app.user_id, search=search.edit()))

class ProgressView(SCView):
	def draw(self, stdscr):
		super().draw(stdscr)
		pl = max(0, self.app.p.get_length())
		pp = min(1, self.app.p.get_position())
		pgrstr = f"{self.app.strfTime(pl*pp/1000)}/{self.app.strfTime(pl/1000)} %s {time.strftime('%X')}"
		icons = '↺'*self.app.repeat
		if (icons): icons = ' '+icons
		stdscr.addstr(0, 1, S(self.app.trackline).cyclefit(self.w-2-len(icons), self.app.tl_rotate//10, start_delay=10).ljust(self.w-2-len(icons))+icons, curses.A_UNDERLINE)
		stdscr.addstr(1, 1, pgrstr % Progress.format_bar(pp, 1, self.w-len(pgrstr))) # TODO: background
		stdscr.addstr(1, 1, pgrstr.split('/')[0], curses.A_BLINK*(not self.app.p.is_playing()))
		if (pl and self.app.p.get_state() == vlc.State.Ended): self.app.playNextTrack()

class LoginView(SCView):
	class PasswordBox(curses.textpad.Textbox):
		def __init__(self, *args, **kwargs):
			super().__init__(*args, **kwargs)
			self.result = str()

		def do_command(self, ch):
			if (ch in (curses.ascii.DEL, curses.ascii.BS, curses.KEY_BACKSPACE)): self.result = self.result[:-1]
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
		login = curses.textpad.Textbox(curses.newwin(y+1, x+ew-13, ey+2, ex+12))
		password = self.PasswordBox(curses.newwin(y+1, x+ew-13, ey+3, ex+12))
		al_login(*map(str.strip, (login.edit(), password.edit())))
		db.save()
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
		if (c == curses.ascii.DEL or c == curses.ascii.BS or c == curses.KEY_BACKSPACE):
			self.q = self.q[:-1]
			if (not self.q):
				self.cancel()
				self.app.waitkeyrelease(c)
		elif (c == '\n' or c == curses.ascii.ESC or c == curses.KEY_EXIT):
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
	l, t = (), int() # ох, костыли...

	def draw(self, stdscr):
		self.h, self.w = stdscr.getmaxyx()
		eh, ew = 8, 23
		ep = stdscr.subpad(eh, ew, (self.h-eh)//2, (self.w-ew)//2)
		ep.addstr(0, 0, '╭'+'─'*(ew-2)+'╮')
		for i in range(1, eh-1): ep.addstr(i, 0, '│'+' '*(ew-2)+'│')
		ep.addstr(eh-2, 0, '╰'+'─'*(ew-2)+'╯')
		for ii, i in enumerate('Are you sure you\nwant to exit?\nPress back again to\nexit or select to\nstay in VKAudio.'.split('\n')): ep.addstr(1+ii, 2, i.center(ew-3), curses.A_BOLD)

	def key(self, c):
		if (c == '\n'): self.app.w.views.pop()
		elif (c == 'q' or c == 'й' or c == curses.ascii.DEL or c == curses.ascii.BS or c == curses.ascii.ESC or c == curses.KEY_BACKSPACE or c == curses.KEY_EXIT): self.app.views.pop()
		else: return super().key(c)
		return True

class App(SCApp):
	def __del__(self):
		try: self.p.stop()
		except Exception: pass

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

		try: self.glib_eventloop = GLib.MainLoop()
		except NameError: pass
		else:
			self.dbus_eventloop = dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
			threading.Thread(target=self.glib_eventloop.run, daemon=True).start()
			#self.dbus_b = dbus.SessionBus()
			#self.dbus_busname = dbus.service.BusName('org.mpris.MediaPlayer2.vkaudio', bus=self.dbus_b)
			#self.dbus_mp = MediaPlayer2(self, self.dbus_busname, '/org/mpris/MediaPlayer2')
			# TODO FIXME ???

		try: notify2.init('VKAudio')
		except Exception: self.notify = None
		else:
			self.notify = notify2.Notification('')
			self.notify.set_category('x-gnome.music')
			self.notify.set_urgency(notify2.URGENCY_LOW)
			self.notify.set_hint('action-icons', True)
			self.notify.connect('closed', noop)
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
		self.tl_rotate = int()

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
		self.tl_rotate = 0
		self.selectPlayingTrack()
		return True

	def playNextTrack(self, force_next=False):
		if (self.repeat and not force_next): self.playTrack(self.track); return
		if (self.play_next): self.playTrack(self.play_next.pop(0)); return
		if (not self.playlist):
			if (not isinstance(self.w.top, AudiosView)): return
			self.playlist = self.w.top.l
			self.pl_peer = self.w.top.peer_id
		self.pl_pos = (self.pl_pos+1) % (len(self.playlist)-1)
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
		if (self.error is not None): return f"Error: {self.error}"
		if (not self.track): return ''
		self.tl_rotate += 1
		return S('%(artist)s — %(title)s' % self.track)

app = App()

@app.onkey('q')
@app.onkey('й')
@app.onkey(curses.ascii.BS)
@app.onkey(curses.ascii.DEL)
@app.onkey(curses.ascii.ESC)
@app.onkey(curses.KEY_BACKSPACE)
@app.onkey(curses.KEY_EXIT)
def back(self, c):
	if (len(self.w.views) <= 1): self.w.addView(QuitView()); return
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
