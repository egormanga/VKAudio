#!/usr/bin/python3
# VK Audio Player

import vlc, notify2, dbus.service, dbus.mainloop.glib
from api import *
from cimg import *
from Scurses import *
from utils import *; logstart('VKAudio')
from gi.repository import GLib

vk_login = str()
vk_pw = str()
db.setfile('~/VKAudio.db')
db.setbackup(False)
db.setsensitive(True)
db.register('vk_login', 'vk_pw')
tokens.require('access_token', 'offline')

class MediaPlayer2(dbus.service.Object):
	class _Properties(metaclass=SlotsMeta):
		app: ...

		def __init__(self, app):
			self.app = app

		def to_dict(self):
			return {k: v.fget(self) if (isinstance(v, property)) else v for k, v in inspect.getmembers(self) if not k.startswith('_') and k not in ('app', 'to_dict')}

	class Properties_org_mpris_MediaPlayer2(_Properties):
		CanQuit = True
		CanRaise = False
		HasTrackList = False # TODO
		Identity = 'VKAudio'
		SupportedUriSchemes = ['']
		SupportedMimeTypes = ['']

	class Properties_org_mpris_MediaPlayer2_Player(_Properties):
		Shuffle = False
		MinimumRate = 0.1
		MaximumRate = 10.0
		CanGoNext = True
		CanGoPrevious = True
		CanPlay = True
		CanPause = True
		CanSeek = True
		CanControl = True

		@property
		def Rate(self):
			return self.app.p.get_rate()

		@Rate.setter
		def Rate(self, rate):
			self.app.p.set_rate(rate)

		@property
		def Volume(self):
			return self.app.p.audio_get_volume()/100

		@Volume.setter
		def Volume(self, volume):
			self.app.p.audio_set_volume(volume*100)

		@property
		def PlaybackStatus(self):
			return 'Playing' if (self.app.p.is_playing()) else 'Paused' if (self.app.track) else 'Stopped'

		@property
		def LoopStatus(self):
			return 'Track' if (self.app.repeat) else 'None'

		@LoopStatus.setter
		def LoopStatus(self, loop):
			self.app.repeat = (loop != 'None')

		@property
		def Metadata(self):
			return dbus.Dictionary(S({
				'mpris:trackid': dbus.ObjectPath(f"/org/mpris/MediaPlayer2/vkaudio/track/{id(self.app.track)}" if (self.app.track) else '/org/mpris/MediaPlayer2/TrackList/NoTrack'),
				'mpris:length': dbus.Int64(max(0, self.app.p.get_length())*1000),
				'mpris:artUrl': self.app.get_cover(self.app.track),
				'xesam:artist': Slist([self.app.track.get('artist')]).strip() or None,
				'xesam:title': self.app.track.get('title'),
				'xesam:url': self.app.track.get('url'),
				'xesam:asText': (lambda x: x if (x and x != 'Текст песни не найден') else None)(self.app.get_lyrics(self.app.track.get('lyrics_id'))),
			}).filter(None), signature='sv')

		@property
		def Position(self):
			return dbus.Int64(max(0, self.app.p.get_time())*1000)

		@Position.setter
		def Position(self, position):
			self.app.p.set_time(position/1000)

	def __init__(self, app, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.app = app
		self.properties_org_mpris_MediaPlayer2 = self.Properties_org_mpris_MediaPlayer2(self.app)
		self.properties_org_mpris_MediaPlayer2_Player = self.Properties_org_mpris_MediaPlayer2_Player(self.app)

	@dbus.service.method('org.mpris.MediaPlayer2')
	def Raise(self):
		pass

	@dbus.service.method('org.mpris.MediaPlayer2')
	def Quit(self):
		self.app.popView()

	@dbus.service.method('org.mpris.MediaPlayer2.Player')
	def Next(self):
		self.app.playNextTrack()

	@dbus.service.method('org.mpris.MediaPlayer2.Player')
	def Previous(self):
		self.app.playPrevTrack()

	@dbus.service.method('org.mpris.MediaPlayer2.Player')
	def Pause(self):
		self.app.pause()

	@dbus.service.method('org.mpris.MediaPlayer2.Player')
	def PlayPause(self):
		self.app.playPause()

	@dbus.service.method('org.mpris.MediaPlayer2.Player')
	def Stop(self):
		self.app.stop()

	@dbus.service.method('org.mpris.MediaPlayer2.Player')
	def Play(self):
		self.app.play()

	@dbus.service.method('org.mpris.MediaPlayer2.Player')
	def Seek(self, offset):
		self.properties_org_mpris_MediaPlayer2_Player.Position += offset

	@dbus.service.method('org.mpris.MediaPlayer2.Player')
	def SetPosition(self, trackid, position):
		self.properties_org_mpris_MediaPlayer2_Player.Position = position

	@dbus.service.method('org.mpris.MediaPlayer2.Player')
	def OpenUri(self, uri):
		pass

	@dbus.service.method(dbus.PROPERTIES_IFACE, in_signature='ss', out_signature='v')
	def Get(self, interface, prop):
		return getattr(getattr(self, 'properties_'+interface.replace('.', '_')), prop)

	@dbus.service.method(dbus.PROPERTIES_IFACE, in_signature='s', out_signature='a{sv}')
	def GetAll(self, interface):
		return getattr(self, 'properties_'+interface.replace('.', '_')).to_dict()

	@dbus.service.method(dbus.PROPERTIES_IFACE, in_signature='ssv')
	def Set(self, interface, prop, value):
		setattr(getattr(self, 'properties_'+interface.replace('.', '_')), prop, value)
		self.PropertiesChanged(interface, {prop: value}, [])

	@dbus.service.signal(dbus.PROPERTIES_IFACE, signature='sa{sv}as')
	def PropertiesChanged(self, interface, changed_props, invalidated_props):
		pass

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
				  {'name': '* Audio Search', 'id': -4},
				  {'name': '* Recommendations', 'id': -5}])
		self.toLoad = True
		self.loading = True

	def item(self, i):
		ret, items = super().item(i)
		if (not ret):
			text, attrs = items[0]
			text = S(self.l[i]['name']).fit(self.w)
			items = [(text, attrs)]
		return (ret, items)

	def select(self):
		if (super().select()): return True
		elif (self.l[self.n]['id'] == -1): self.app.w.addView(AudiosView(self.app.user_id))
		elif (self.l[self.n]['id'] == -2): self.app.w.addView(AlbumsView())
		elif (self.l[self.n]['id'] == -3): self.app.w.addView(FriendsView())
		elif (self.l[self.n]['id'] == -4): self.app.w.addView(AudioSearchView())
		elif (self.l[self.n]['id'] == -5): self.app.w.addView(AlbumsView(recomms=True))
		else: self.app.w.addView(AudiosView(self.l[self.n]['id'], im=True))

	def load(self):
		if (super().load()): return True
		try: r = dialogs(count=self.h-1, start_message_id=(self.l[-1].next_value or None), extended=True, parse_attachments=False)
		except VKAlLoginError: self.app.w.addView(LoginView(self.load)); return
		if (len(self.l) > 3): self.l.pop()
		for i in r['items']:
			try:
				if (i['conversation']['peer']['type'] == 'user'): u = S(r['profiles'])['id', i['conversation']['peer']['id']][0]; self.l.append(S(u)&{'name': ' '.join(S(u)@['first_name', 'last_name'])})
				elif (i['conversation']['peer']['type'] == 'chat'): self.l.append({'name': i['conversation']['chat_settings']['title'], 'id': i['conversation']['peer']['id']})
				elif (i['conversation']['peer']['type'] == 'group'): self.l.append(S(r['groups'])['id', -i['conversation']['peer']['id']][0])
			except IndexError: pass
		self.l.append(self.LoadItem(r.get('has_more', bool(r)), i['conversation']['last_message_id']-1))

class FriendsView(SCLoadingSelectingListView):
	def __init__(self):
		super().__init__([])
		self.toLoad = True
		self.loading = True

	def item(self, i):
		ret, items = super().item(i)
		if (not ret):
			text, attrs = items[0]
			text = S(self.l[i]['name']).fit(self.w)
			items = [(text, attrs)]
		return (ret, items)

	def select(self):
		if (super().select()): return True
		self.app.w.addView(AudiosView(self.l[self.n]['id']))

	def load(self):
		if (super().load()): return True
		try: r = API.audio.getFriends(exclude=S(',').join(S(self.l[:-1])@['id']))
		except VKAlLoginError: self.app.w.addView(LoginView(self.load)); return
		if (self.l): self.l.pop()
		l = user(r)
		if (not l or l[0] in self.l): self.l.append(self.LoadItem(False)); return
		self.l += l
		self.l.append(self.LoadItem())

class AlbumsView(SCLoadingSelectingListView):
	def __init__(self, *, recomms=False):
		super().__init__([])
		self.recomms = recomms
		self.toLoad = True
		self.loading = True

	def item(self, i):
		ret, items = super().item(i)
		if (not ret):
			text, attrs = items[0]
			text = S(self.l[i]['title']).fit(self.w)
			items = [(text, attrs)]
		return (ret, items)

	def select(self):
		if (super().select()): return True
		self.app.w.addView(AudiosView(self.l[self.n]['owner_id'], album_id=self.l[self.n]['id'], access_hash=self.l[self.n]['access_hash']))

	def load(self):
		if (super().load()): return True
		try:
			if (self.recomms):
				if (len(self.l) < 2): r = API.audio.getAlbums(owner_id=self.app.user_id, section='recoms'); r['next'] = 0
				else: r = S(API.audio.getRecommendations(offset=self.l[-1].next_value)).translate({'items': 'playlists'})
			else: r = API.audio.getAlbums(owner_id=self.app.user_id)
		except VKAlLoginError: self.app.w.addView(LoginView(self.load)); return
		if (self.l): self.l.pop()
		self.l += r['items']
		self.l.append(SCLoadingListView.LoadItem(r.get('next') is not None, r.get('next')))

class AudiosView(SCLoadingSelectingListView):
	def __init__(self, peer_id, album_id=-1, access_hash=None, search=None, im=False):
		super().__init__([])
		self.peer_id, self.album_id, self.access_hash, self.search, self.im = peer_id, album_id, access_hash, search, im
		self.toLoad = True
		self.loading = True
		self.toReselect = True

	def draw(self, stdscr):
		try: # FIXME crash?
			if (super().draw(stdscr)): return True
		except curses.error: pass
		if (self.toReselect and not isinstance(self.l[0], SCLoadingListView.LoadItem)):
			self.app.selectPlayingTrack()
			self.toReselect = False

	def key(self, c):
		if (c == 'n' or c == 'т'):
			t = self.l[self.n]
			for ii, i in enumerate(self.app.play_next):
				if (isinstance(i, dict) and al_audio_eq(i, t)): del self.app.play_next[ii]; self.touch(); return
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
			url = al_audio_get_url(self.app.user_id, self.l[self.n])
			print(f"Downloading: {url}")
			os.system(f"""wget "{url}" -O "{'%(artist)s - %(title)s.mp3' % self.l[self.n]}" -q --show-progress""")
			curses.reset_prog_mode()
		elif (c == 'l' or c == 'д'):
			self.app.w.addView(LyricsView(self.l[self.n]['lyrics_id']))
		else: return super().key(c)
		return True

	@staticmethod
	@lrucachedfunction
	def _color(cover): return tuple(i*1000//255 for i in pixel_color(openimg(cover)))

	@classmethod
	def _pair(cls, cover):
		if (not curses.can_change_color()): return 0#curses.COLORS < 9 or
		r, g, b = cls._color(cover)
		color = 2#random.randrange(9, curses.COLORS)
		curses.init_color(color, r, g, b)
		pair = 2#random.randrange(9, curses.COLORS)
		curses.init_pair(pair, color, curses.COLOR_WHITE if (max(r, g, b) < 500) else curses.COLOR_BLACK)
		return curses.color_pair(pair)

	def item(self, i):
		ret, items = super().item(i)
		if (not ret):
			for jj, j in enumerate(self.app.play_next):
				if (al_audio_eq(j, self.l[i])): pn_pos = str(jj+1); break
			else: pn_pos = ''
			t_attrs = (pn_pos+' ' if (pn_pos) else '')+('HQ ' if (self.l[i].get('is_hq')) else '')+self.app.strfTime(self.l[i]['duration'])
			attrs = items[0][1]
			text1 = S(('%(artist)s — %(title)s' % self.l[i]) + ' '*bool(self.l[i].get('subtitle')))
			text2 = S(self.l[i].get('subtitle', '')).fit(self.w - text1.fullwidth() - len(t_attrs) - 1)
			text1 = text1.fit(self.w - text2.fullwidth() - len(t_attrs) - 1)
			text3 = t_attrs.rjust(self.w - text1.fullwidth() - text2.fullwidth())
			if (not attrs & curses.A_STANDOUT): color = 0
			else:
				cover = self.app.get_cover(self.l[i])
				color = self._pair(cover) if (cover) else 0
			items = [(text1, attrs | color), (text2, attrs | color | curses.A_DIM*(not attrs & curses.A_STANDOUT)), (text3, attrs | color)]
		return (ret, items)

	def select(self):
		if (super().select()): return True
		self.app.setPlaylist(self.l, self.n, self.peer_id)
		self.app.playTrack()

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
		if (super().load()): return True
		try:
			if (self.search):
				r = self._search(owner_id=self.peer_id, q=self.search, offset=self.l.pop().next_value)
				l = r['playlist']['list'] if (r['playlist']) else []
				if (l):
					self.album_id, self.access_hash = S(r['playlist'])@['id', 'access_hash']
					self.search = False
			elif (self.im):
				r = self._history(peer_id=self.peer_id, media_type='audio', count=self.h, start_from=self.l.pop().next_value)
				l = S(r['items'])@['attachment']@['audio']
			else:
				r = self._get(owner_id=self.peer_id, album_id=self.album_id, access_hash=self.access_hash, offset=self.l.pop().next_value)
				l = r['list']
		except VKAlLoginError: self.app.w.addView(LoginView(self.load)); return
		for i in l:
			if (self.l and self.l[-1] == i): continue
			self.l.append(i)
		self.l.append(SCLoadingListView.LoadItem(bool(r.get('next_from')) and r.get('has_more', bool(l)), r.get('next_from')))

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
		self.text = S(self.app.get_lyrics(self.lyrics_id)).wrap(self.ew-3)

	def draw(self, stdscr):
		if (not self.touched): return True
		self.touched = False
		self.h, self.w = stdscr.getmaxyx()
		ep = stdscr.subpad(self.eh, self.ew, (self.h-self.eh)//2, (self.w-self.ew)//2)
		ep.addstr(0, 0, '╭'+'─'*(self.ew-2)+'╮')
		for i in range(1, self.eh-1):
			ep.addstr(i, 0, '│'+' '*(self.ew-2)+'│')
		ep.addstr(self.eh-2, 0, '╰'+'─'*(self.ew-2)+'╯')
		for ii, i in enumerate(self.text.split('\n')[self.offset:self.eh-3+self.offset]):
			ep.addstr(ii+1, 2, i)

	def key(self, c):
		if (c == curses.KEY_UP):
			self.offset = max(0, self.offset-1)
			self.touch()
		elif (c == curses.KEY_DOWN):
			self.offset = min(self.offset+1, self.text.count('\n')-self.eh+4)
			self.touch()
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
				try: ch = self.win.get_wch()
				except curses.error: continue # TODO FIXME
				if (validate): ch = validate(ch)
				if (not ch): continue
				if (not self.do_command(ch)): break
				self.win.refresh()
			return self.result

	def draw(self, stdscr):
		if (not self.touched): return True
		self.touched = False
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
		self.app.w.popView()
		self.app.w.addView(AudiosView(self.app.user_id, search=search.edit()))

class ProgressView(SCView):
	def __init__(self):
		super().__init__()
		self.paused = None
		self.repeat = None
		self.tm = None

	def draw(self, stdscr):
		paused = (not self.app.p.is_playing())
		repeat = self.app.repeat
		tm = time.strftime('%X')

		if ((paused, repeat, tm) != (self.paused, self.repeat, self.tm)): self.touch()
		if (super().draw(stdscr)): return True
		self.paused, self.repeat, self.tm = paused, repeat, tm

		pl = max(0, self.app.p.get_length())
		pt = max(0, self.app.p.get_time())
		pp = min(1, self.app.p.get_position())
		pgrstr = (self.app.strfTime(pt/1000), self.app.strfTime(pl/1000), tm)
		icons = '↺'*repeat
		if (icons): icons = ' '+icons
		stdscr.addstr(0, 1, S(self.app.trackline).cyclefit(self.w-2-len(icons), self.app.tl_rotate, start_delay=10).ljust(self.w-2-len(icons))+icons, curses.A_UNDERLINE)
		stdscr.addstr(1, 1, pgrstr[0], curses.A_BLINK*paused)
		stdscr.addstr(1, 1+len(pgrstr[0]), '/'+pgrstr[1]+' │')
		stdscr.addstr(1, 4+len(str().join(pgrstr[:2])), Progress.format_bar(pp, 1, self.w-len(str().join(pgrstr))-4, border=''), curses.color_pair(1))
		stdscr.addstr(1, self.w-2-len(pgrstr[-1]), '▏'+pgrstr[-1])

class LoginView(SCView):
	def __init__(self, callback=None):
		super().__init__()
		self.callback = callback or noop

	class LoginBox(curses.textpad.Textbox):
		def do_command(self, ch):
			self._update_max_yx()
			y, x = self.win.getyx()
			self.lastcmd = ch
			if (ch in (curses.ascii.STX, curses.KEY_LEFT, curses.ascii.BS, curses.ascii.DEL, curses.KEY_BACKSPACE)):
				if (x > 0): self.win.move(y, x-1)
				elif (y == 0): pass
				elif (self.stripspaces): self.win.move(y-1, self._end_of_line(y-1))
				else: self.win.move(y-1, self.maxx)
				if (ch in (curses.ascii.BS, curses.ascii.DEL, curses.KEY_BACKSPACE)): self.win.delch()
			return super().do_command(ch)

		def set(self, s):
			for i in s:
				self._insert_printable_char(ord(i))
			self.win.refresh()

	class PasswordBox(curses.textpad.Textbox):
		def __init__(self, *args, **kwargs):
			super().__init__(*args, **kwargs)
			self.result = str()

		def do_command(self, ch):
			self._update_max_yx()
			y, x = self.win.getyx()
			self.lastcmd = ch
			if (ch in (curses.ascii.STX, curses.KEY_LEFT, curses.ascii.BS, curses.ascii.DEL, curses.KEY_BACKSPACE)):
				self.result = self.result[:-1]
				if (x > 0): self.win.move(y, x-1)
				elif (y == 0): pass
				elif (self.stripspaces): self.win.move(y-1, self._end_of_line(y-1))
				else: self.win.move(y-1, self.maxx)
				if (ch in (curses.ascii.BS, curses.ascii.DEL, curses.KEY_BACKSPACE)): self.win.delch()
			return super().do_command(ch)

		def _insert_printable_char(self, ch):
			self.result += chr(ch)
			return super()._insert_printable_char('*')

		def set(self, s):
			for i in s:
				self._insert_printable_char(ord(i))
			self.win.refresh()

		def gather(self):
			return self.result

	def draw(self, stdscr):
		global vk_login, vk_pw
		if (not self.touched): return True
		self.touched = False

		l, p = vk_login, ub64(vk_pw)
		try: al_login(l, p)
		except VKAlLoginError: pass
		else: self.app.w.popView(); self.callback(); return

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
		login = self.LoginBox(curses.newwin(y+1, x+ew-13, ey+2, ex+12))
		login.set(l)
		password = self.PasswordBox(curses.newwin(y+1, x+ew-13, ey+3, ex+12))
		password.set(p)

		while (True):
			ep.addstr(2, 2, 'VK Login:', curses.A_BOLD); ep.refresh()
			try: l = login.edit().strip()
			finally: ep.addstr(2, 2, 'VK Login:')

			ep.addstr(3, 2, 'Password:', curses.A_BOLD); ep.refresh()
			try: p = password.edit().strip()
			finally: ep.addstr(3, 2, 'Password:')

			try: al_login(l, p)
			except VKAlLoginError as ex: ep.addstr(1, 2, str(ex).center(ew-4)); continue
			else: vk_login, vk_pw = l, b64(p); break

		db.save()
		self.app.w.popView()
		self.callback()

class HelpView(SCView):
	def draw(self, stdscr):
		if (not self.touched): return True
		self.touched = False
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
		self.app.w.popView()
		self.app.w.top.touch()
		return True

class FindView(SCView): # TODO: more intuitive control?
	def __init__(self):
		super().__init__()
		self.q = '/'
		self.found = None

	def init(self):
		self.app.top.focus = 1

	def draw(self, stdscr):
		if (not self.touched): return True
		self.touched = False
		self.app.top.p[1].views[-2].touch()
		self.app.top.p[1].views[-2].draw(stdscr)
		self.h, self.w = stdscr.getmaxyx()
		with lc(''): stdscr.addstr(0, 0, self.q.encode(locale.getpreferredencoding()))

	def key(self, c):
		if (c in (curses.KEY_UP, curses.KEY_DOWN, curses.KEY_LEFT, curses.KEY_RIGHT)):
			self.app.w.top.key(c)
		elif (c == curses.ascii.DEL or c == curses.ascii.BS or c == curses.KEY_BACKSPACE):
			self.q = self.q[:-1]
			self.touch()
			if (not self.q):
				self.cancel()
				self.app.waitkeyrelease(c)
		elif (c == curses.ascii.NL or c == curses.ascii.ESC or c == curses.KEY_EXIT):
			self.cancel()
			if (c == curses.ascii.NL): self.app.w.top.key(c)
		elif (c.ch.isprintable()):
			self.q += c.ch
			self.touch()
			q = self.q[1:].casefold()
			for i in range(self.app.w.top.n, len(self.app.w.top.l)):
				t = self.app.w.top.l[i]
				try: t['artist']
				except (TypeError, KeyError): continue
				if (q in ('%(artist)s — %(title)s' % t).casefold()):
					self.app.w.top.selectAndScroll(i)
					self.found = i
					break
			else: self.found = None
		return True

	def cancel(self):
		self.app.top.focus = 0
		self.app.top.p[1].popView()
		self.app.top.p[1].top.touch()

class QuitView(SCView):
	l, t = (), int()

	def draw(self, stdscr):
		if (not self.touched): return True
		self.touched = False
		self.h, self.w = stdscr.getmaxyx()
		eh, ew = 8, 23
		ep = stdscr.subpad(eh, ew, (self.h-eh)//2, (self.w-ew)//2)
		ep.addstr(0, 0, '╭'+'─'*(ew-2)+'╮')
		for i in range(1, eh-1): ep.addstr(i, 0, '│'+' '*(ew-2)+'│')
		ep.addstr(eh-2, 0, '╰'+'─'*(ew-2)+'╯')
		for ii, i in enumerate('Are you sure you\nwant to exit?\nPress back again to\nexit or select to\nstay in VKAudio.'.split('\n')): ep.addstr(1+ii, 2, i.center(ew-3), curses.A_BOLD)

	def key(self, c):
		if (c == curses.ascii.NL): self.app.w.popView(); self.app.w.top.touch()
		elif (c == 'q' or c == 'й' or c == curses.ascii.DEL or c == curses.ascii.BS or c == curses.ascii.ESC or c == curses.KEY_BACKSPACE or c == curses.KEY_EXIT): self.app.popView()
		else: return super().key(c)
		return True

class App(SCApp):
	def __del__(self):
		try: self.stop()
		except AttributeError: pass
		try: self.update_all()
		except Exception: pass

	def init(self):
		super().init()
		curses.use_default_colors()
		try: curses.init_pair(1, curses.COLOR_WHITE, 8)
		except curses.error: curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)  # fbcon
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
			self.dbus = dbus.SessionBus()
			self.mpris = MediaPlayer2(self, dbus.service.BusName('org.mpris.MediaPlayer2.vkaudio', bus=self.dbus), '/org/mpris/MediaPlayer2')
			self.update_all()

		try: raise Exception#notify2.init('VKAudio')
		except Exception: self.notify = None
		else:
			self.notify = notify2.Notification('', icon='media-playback-start')
			self.notify.set_category('x-gnome.music')
			self.notify.set_urgency(notify2.URGENCY_LOW)
			self.notify.set_hint('action-icons', True)
			self.notify.connect('closed', noop)
			self.notify.add_action('media-skip-backward', 'Previous track', lambda *_: self.playPrevTrack())
			self.notify.add_action('media-playback-pause', 'Pause', lambda *_: self.playPause())
			self.notify.add_action('media-skip-forward', 'Next track', lambda *_: self.playNextTrack())

		self.user_id = user()[0]['id']

		self.playlist = list()
		self.pl_pos = -1
		self.pl_peer = int()
		self.play_next = list()
		self._track = dict()
		self.error = None
		self.repeat = bool()
		self.clicked = bool()
		self.tl_rotate = int()

		self.w = self.top.p[0]

	_lastproc = int()
	_lastpb = None
	_lastmd = None
	_lastpos = int()
	def proc(self):
		if (time.time()-self._lastproc >= 0.1):
			self._lastproc = time.time()

			pb = self.mpris.properties_org_mpris_MediaPlayer2_Player.PlaybackStatus
			if (pb != self._lastpb):
				self._lastpb = pb
				self.update_properties(PlaybackStatus=pb)

			md = self.mpris.properties_org_mpris_MediaPlayer2_Player.Metadata
			if (md != self._lastmd):
				self._lastmd = md
				self.update_properties(Metadata=md)

			pos = self.mpris.properties_org_mpris_MediaPlayer2_Player.Position
			if (abs(pos-self._lastpos) > 500*1000):
				self._lastpos = pos
				if (self.p.is_playing()): self.update_properties(Position=pos)
		if (self.p.get_length() > 0 and self.p.get_state() == vlc.State.Ended): self.playNextTrack()

	@staticmethod
	def strfTime(t): return time.strftime('%H:%M:%S', time.gmtime(t)).lstrip('0').lstrip(':')

	@cachedfunction
	def get_lyrics(self, lyrics_id):
		return API.audio.getLyrics(lyrics_id=lyrics_id)['text'] if (lyrics_id is not None) else ''

	@cachedfunction
	def get_cover(self, track):
		url = (track.get('covers') or ('',))[-1]
		if (not url): return None
		cache_folder = os.path.expanduser('~/.cache/VKAudio/covers')
		os.makedirs(cache_folder, exist_ok=True)
		path = os.path.join(cache_folder, md5(url)+os.path.splitext(url)[1])
		open(path, 'wb').write(requests.get(url).content)
		return 'file://'+os.path.abspath(path)

	def playTrack(self, t=None, *, notify=True):
		if (t is None): return self.playTrack(self.playlist[self.pl_pos])
		self.error = None
		self.stop()
		try:
			self.p.set_mrl(al_audio_get_url(self.user_id, t))
			self.play()
		except Exception as ex: self.error = ex; return False
		if (notify): self.notifyPlaying(t)
		self.track = t
		self.tl_rotate = 0
		self.selectPlayingTrack()
		return True

	def playNextTrack(self, force_next=False):
		if (self.play_next): self.playTrack(self.play_next.pop(0)); return
		if (self.repeat and not force_next): self.playTrack(self.track, notify=False); return
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

	def play(self):
		self.p.play()
		self.update_properties('PlaybackStatus', 'Metadata', 'Position')

	def pause(self):
		self.p.pause()
		self.update_properties('PlaybackStatus')

	def playPause(self):
		self.p.pause()
		self.update_properties('PlaybackStatus')

	def stop(self):
		self.p.stop()
		if (self.notify is not None): self.notify.close()
		self.track = dict()
		self.update_properties('PlaybackStatus', 'Metadata')
		self.w.top.s = -1
		self.w.top.touch()

	def setPosition(self, position):
		if (not self.p.is_playing()): return
		self.p.set_position(position)
		self.update_properties('Position')

	def setPlaylist(self, l, n=-1, peer_id=int()):
		self.playlist = l
		self.pl_pos = n
		self.pl_peer = peer_id

	def playNext(self, t):
		self.play_next.append(t)
		for ii, i in enumerate(self.playlist):
			if (isinstance(i, dict) and al_audio_eq(i, t)): self.pl_pos = ii; break
		self.w.top.touch()

	def toggleRepeat(self):
		self.repeat = not self.repeat
		self.update_properties('LoopStatus')

	def seekRew(self):
		self.setPosition(self.p.get_position()-0.01)

	def seekFwd(self):
		self.setPosition(self.p.get_position()+0.01)

	def notifyPlaying(self, t):
		try:
			self.notify.update(t['title'], t['artist'])
			self.notify.show()
		except Exception: pass

	def update_properties(self, *invalidated_props, **changed_props):
		o = self.mpris.properties_org_mpris_MediaPlayer2_Player
		changed_props.update({i: (lambda v: v.fget(o) if (isinstance(v, property)) else v)(getattr(o, i)) for i in invalidated_props if i not in changed_props})
		self.mpris.PropertiesChanged('org.mpris.MediaPlayer2.Player', changed_props, [])

	def update_all(self):
		self.mpris.PropertiesChanged('org.mpris.MediaPlayer2.Player', self.mpris.properties_org_mpris_MediaPlayer2_Player.to_dict(), [])

	@property
	def track(self):
		return self._track

	@track.setter
	def track(self, track):
		self._track = track
		self.update_properties('Metadata')

	@property
	def trackline(self):
		if (self.error is not None): return f"Error: {self.error}"
		if (not self.track): return ''
		self.tl_rotate += 1
		return '%(artist)s — %(title)s' % self.track

app = App(proc_rate=10)

@app.onkey('q')
@app.onkey('й')
@app.onkey(curses.ascii.BS)
@app.onkey(curses.ascii.DEL)
@app.onkey(curses.ascii.ESC)
@app.onkey(curses.KEY_BACKSPACE)
@app.onkey(curses.KEY_EXIT)
def back(self, c):
	if (len(self.w.views) <= 1): self.w.addView(QuitView()); return
	self.w.popView()

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
	self.setPosition(0.1*('1234567890'.index(c.ch)))

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
	self.w.top.touch()
	self.stdscr.redrawwin()

@app.onkey(curses.KEY_MOUSE)
def mouse(self, c):
	try: id, x, y, z, bstate = curses.getmouse()
	except (curses.error, IndexError): id = x = y = z = bstate = 0
	h, w = self.stdscr.getmaxyx()
	if (y < h-2):
		if (bstate == curses.BUTTON4_PRESSED): self.w.top.t = max(self.w.top.t-3, 0); self.w.top.touch()
		elif (bstate == curses.REPORT_MOUSE_POSITION or bstate == 2097152 and len(self.w.top.l) > h): self.w.top.t = min(self.w.top.t+3, len(self.w.top.l)-h+2-(self.w.top.l[-1] is None)); self.w.top.touch()
		elif (bstate == curses.BUTTON1_PRESSED):
			if (isinstance(self.w.top, QuitView)): self.w.popView(); return
			self.w.top.n = self.w.top.t+y
			if (time.time() < self.clicked): self.w.top.select(); self.clicked = True
			self.w.top.touch()
		elif (bstate == curses.BUTTON1_RELEASED):
			self.clicked = False if (self.clicked == True) else time.time()+0.2
		elif (bstate == curses.BUTTON3_PRESSED):
			if (isinstance(self.w.top, QuitView)): self.popView(); return
			back(self, c)
	elif (y == h-2 and x >= w-2):
		if (bstate == curses.BUTTON1_PRESSED): self.toggleRepeat()
	elif (y == h-1):
		if (x < 14):
			if (bstate in (curses.BUTTON1_PRESSED, curses.BUTTON3_PRESSED, curses.BUTTON3_RELEASED)):
				self.pause()
			elif (bstate == curses.BUTTON4_PRESSED):
				self.playPrevTrack()
			elif (bstate == curses.REPORT_MOUSE_POSITION or bstate == 2097152):
				self.playNextTrack()

		elif (x <= w-12):
			if (bstate == curses.BUTTON1_PRESSED):
				self.setPosition((x-14)/(w-12-14+1))
			elif (bstate == curses.BUTTON4_PRESSED):
				self.seekRew()
			elif (bstate == curses.REPORT_MOUSE_POSITION or bstate == 2097152):
				self.seekFwd()

def main():
	global app
	app.addView(VKAudioView())
	try: app.run()
	finally: app.__del__()

if (__name__ == '__main__'):
	logstarted()
	db.load()
	user()
	exit(main())
else: logimported()

# by Sdore, 2020
