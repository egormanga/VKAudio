#!/usr/bin/python3
# VK Audio Player

import vlc, html, vaud, curses, locale, random
from api import *
from curses.textpad import Textbox
from utils import *; logstart('VKAudio')

db.setfile(os.path.dirname(os.path.realpath(sys.argv[0]))+'/VKAudio.db')
db.setbackup(False)
tokens.require('access_token', 'messages,offline')

def main(stdscr, user_id):
	curses.curs_set(False)
	curses.use_default_colors()
	stdscr.nodelay(True)
	curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
	curses.mouseinterval(0)

	p = vlc.MediaPlayer()
	p.get_instance().log_unset()
	p.audio_set_volume(100)

	url_decoder = vaud.Decoder(user_id)

	def login(): # TODO: close on ^C (somehow)
		global vk_sid
		eh, ew = 6, 48
		ey, ex = (h-eh)//2, (w-ew)//2
		ep = curses.newwin(eh, ew, ey, ex)
		ep.addstr(0, 0, '╭'+'─'*(ew-2)+'╮')
		for i in range(1, eh-1): ep.addstr(i, 0, '│'+' '*(ew-2)+'│')
		ep.addstr(eh-2, 0, '╰'+'─'*(ew-2)+'╯')
		ep.addstr(1, 2, 'Authorization'.center(ew-4))
		ep.addstr(2, 2, 'VK Login:')
		ep.addstr(3, 2, 'Password:')
		ep.refresh()
		login, password = Textbox(stdscr.subpad(1, ew-13, ey+2, ex+12)), Textbox(stdscr.subpad(1, ew-13, ey+3, ex+12))
		login.edit(); password.edit()
		al_login(*map(str.strip, (login.gather(), password.gather())))
	def loadDialogs():
		nonlocal ll
		if (ll <= 1): stdscr.addstr(0, 0, 'Loading'.center(stdscr.getmaxyx()[1]), curses.A_STANDOUT); stdscr.refresh()
		if (len(l) < 2): l.insert(-1, {'name': '* My Audios', 'id': -1})
		r = dialogs(offset=len(l)-1, extended=1)
		for i in r['items']:
			if (i['conversation']['peer']['type'] == 'user'): u = S(r['profiles'])['id', i['conversation']['peer']['id']][0]; l.insert(-1, S(u)&{'name': ' '.join(S(u)@['first_name', 'last_name'])})
			elif (i['conversation']['peer']['type'] == 'chat'): l.insert(-1, {'name': i['conversation']['chat_settings']['title'], 'id': i['conversation']['peer']['id']})
			elif (i['conversation']['peer']['type'] == 'group'): l.insert(-1, S(r['groups'])['id', -i['conversation']['peer']['id']][0])
		l[-1] = bool(r['items'])
		ll = len(l)-1
	def loadAudios():
		nonlocal ll
		if (ll <= 1): stdscr.addstr(0, 0, 'Loading'.center(stdscr.getmaxyx()[1]), curses.A_STANDOUT); stdscr.refresh()
		if (peer_id == -1): loadOwnAudios(); return
		r = API.messages.getHistoryAttachments(peer_id=peer_id, media_type='audio', start_from=l[-1])
		for i in S(r['items'])@['attachment']@['audio']:
			if (len(l) < 2 or l[-2] != i): l.insert(-1, i)
		l[-1] = r.get('next_from')
		ll = len(l)-1
	def loadOwnAudios(): # TODO: playlists, owners
		nonlocal ll
		if (not getvksid()): login()
		r = API.audio.get(owner_id=user_id, offset=l[-1])
		for i in r['list']: l.insert(-1, {
			'title': html.unescape(i[3]),
			'artist': html.unescape(i[4]),
			'duration': i[5],
			'is_hq': False, # TODO ???
			'url': url_decoder.decode(i[2]),
		})
		l[-1] = str(r.get('nextOffset')) if (r['hasMore']) else None
		ll = len(l)-1

	def scrollToTop():
		nonlocal n, t
		n = t = 0
	def scrollToSelected(): # TODO: O(1)
		nonlocal n, t
		while (t > n): t = max(t-1, 0)
		while (t+h <= n): t = min(t+1, ll-h+1)
	def selectItem():
		nonlocal mode
		if (mode == -1): mode = 0
		elif (mode == 0): selectDialog()
		elif (mode == 1): playTrack()
		if (lmode != mode): scrollToTop()
	def goBack():
		nonlocal mode
		mode -= 1
		scrollToTop()
	def toggleRepeat():
		nonlocal repeat
		repeat = not repeat
	def selectDialog():
		nonlocal n, mode, peer_id
		if (n > ll): n -= 1; return
		if (type(l[n]) == bool): loadDialogs(); return
		peer_id = l[n]['id']
		mode = 1
	def playTrack():
		nonlocal n, cs, cu, track
		if (n > ll): n -= 1; return
		if (type(l[n]) == str): loadAudios(); return
		cs, cu = n, peer_id
		p.stop()
		stdscr.addstr(h, 1, 'Loading...')
		try: p.set_mrl(l[n]['url']); p.play()
		except: track = 'Error'
	def playNextTrack(force_next=False):
		nonlocal l, n, cs, repeat, play_next
		if (not repeat or force_next):
			if (play_next): n = play_next.pop(0)
			else: n = (cs+1) % len(l)
		playTrack()
		scrollToSelected()

	def strfTime(t): return time.strftime('%H:%M:%S', time.gmtime(t)).lstrip('0').lstrip(':')
	def debugOut(*s, sep=' '): s = sep.join(map(str, s)); stdscr.addstr(0, (stdscr.getmaxyx()[1]-len(s))//2-1, s, curses.A_STANDOUT)

	n, t, ll, ln, mode = (int(),)*5
	cl, cs, cu, lmode = (-1,)*4
	l = list()
	peer_id = int()
	track = str()
	repeat = bool()
	play_next = list()
	clicked = bool()

	try:
		while (True):
			h, w = stdscr.getmaxyx(); h -= 2
			if (mode >= 0): stdscr.erase()
			if (mode == -2): break
			elif (mode == -1):
				eh, ew = 8, 23
				ep = stdscr.subpad(eh, ew, (h-eh)//2, (w-ew)//2)
				ep.addstr(0, 0, '╭'+'─'*(ew-2)+'╮')
				for i in range(1, eh-1): ep.addstr(i, 0, '│'+' '*(ew-2)+'│')
				ep.addstr(eh-2, 0, '╰'+'─'*(ew-2)+'╯')
				for ii, i in enumerate('Are you sure you\nwant to exit?\nPress the key again\nto exit or select\nto stay.'.split('\n')): ep.addstr(1+ii, 2, i.center(ew-3), curses.A_BOLD)
			elif (mode == 0):
				if (lmode != mode): l = [True]; loadDialogs(); n = ln; lmode = mode
				for i in range(t, min(t+h, len(l))):
					if (l[i] == True): stdscr.addstr(i-t, 0, 'Load more...', curses.A_STANDOUT*(i==n)); continue
					elif (l[i] == False): stdscr.addstr(i-t, 0, 'End.', curses.A_STANDOUT*(i==n)); ll = len(l)-2; continue
					stdscr.addstr(i-t, 0, S(l[i]['name']).fit(w), curses.A_STANDOUT*(i==n))
			elif (mode == 1):
				if (lmode != mode): l = [str()]; loadAudios(); ln = n; n = 0; lmode = mode
				for i in range(t, min(t+h, len(l))):
					if (type(l[i]) == str): stdscr.addstr(i-t, 0, 'Load more...', curses.A_STANDOUT*(i==n)); continue
					elif (not l[i]): stdscr.addstr(i-t, 0, 'End.', curses.A_STANDOUT*(i==n)); ll = len(l)-2; continue
					title = '%s — %s' % (l[i]['artist'], l[i]['title'])
					title_attrs = ' '.join((str(play_next.index(i)+1) if (i in play_next) else '', 'HQ'*l[i]['is_hq'], strfTime(l[i]['duration'])))
					stdscr.addstr(i-t, 0, S(title).fit(w-len(title_attrs)-2)+' '+title_attrs.rjust(w-len(title)-1), curses.A_STANDOUT*(i==n) | curses.A_BOLD*(i==cs and peer_id==cu))
			pl = max(0, p.get_length())
			pp = min(1, p.get_position())
			pgrstr = f"{strfTime(pl*pp/1000)}/{strfTime(pl/1000)} %s {time.strftime('%X')}"
			if (mode == 1 and peer_id == cu and cs != -1): track = '%(artist)s — %(title)s' % l[cs]
			stdscr.addstr(h, 1, S(track).fit(w-2-repeat*2).ljust(w-3)+' ↺'[repeat], curses.A_UNDERLINE)
			stdscr.addstr(h+1, 1, pgrstr % Progress.format_bar(pp, 1, w-len(pgrstr)))
			stdscr.addstr(h+1, 1, pgrstr.split('/')[0], curses.A_BLINK*(not p.is_playing()))
			if (p.get_state() == vlc.State.Ended): playNextTrack()

			c = stdscr.getch()
			if (c != -1): cl = c
			if (c == 1): pass
			elif (c == curses.KEY_UP):
				n = max(n-1, 0)
				scrollToSelected()
			elif (c == curses.KEY_DOWN):
				n = min(n+1, ll)
				scrollToSelected()
			elif (c == curses.KEY_PPAGE):
				n = max(n-h, 0)
				scrollToSelected()
			elif (c == curses.KEY_NPAGE):
				n = min(n+h, ll)
				scrollToSelected()
			elif (c == curses.KEY_HOME):
				n = 0
				scrollToSelected()
			elif (c == curses.KEY_END):
				n = ll
				scrollToSelected()
			elif (c == curses.KEY_LEFT):
				if (mode == 1): p.set_position(p.get_position()-0.01)
			elif (c == curses.KEY_RIGHT):
				if (mode == 1): p.set_position(p.get_position()+0.01)
			elif (c in range(ord('0'), ord('9')+1)):
				if (p.is_playing()): p.set_position(0.1*('1234567890'.index(chr(c))))
			elif (c == ord(' ') or c == ord('p')):
				if (mode == 1): p.pause()
			elif (c == ord('\n')):
				selectItem()
			elif (c == ord('q') or c == ord('\033') or c == curses.KEY_BACKSPACE or c == curses.KEY_EXIT): goBack()
			elif (c == ord('a')):
				playNextTrack(force_next=True)
			elif (c == ord('s')):
				p.stop()
				cs = -1
			elif (c == ord('r')):
				toggleRepeat()
			elif (c == ord('n')):
				play_next.append(n)
			elif (c == curses.KEY_MOUSE):
				try: id, x, y, z, bstate = curses.getmouse()
				except curses.error: id = x = y = z = bstate = 0
				if (bstate == curses.BUTTON4_PRESSED): t = max(t-3, 0)
				elif (bstate == curses.REPORT_MOUSE_POSITION and ll > h): t = min(t+3, ll-h+1)
				else:
					if (y < h):
						if (bstate == curses.BUTTON1_PRESSED):
							if (mode < 0): selectItem()
							else:
								n = t+y
								if (time.time() < clicked): selectItem(); clicked = True
						elif (bstate == curses.BUTTON1_RELEASED): clicked = False if (clicked == True) else time.time()+0.2
						elif (bstate == curses.BUTTON3_PRESSED): goBack()
					elif (y == h+1 and 14 <= x <= w-12):
						if (bstate == curses.BUTTON1_PRESSED or bstate == curses.REPORT_MOUSE_POSITION):
							if (p.is_playing()): p.set_position((x-14)/(w-12-14+1))
					elif (y == h and x >= w-2):
						if (bstate == curses.BUTTON1_PRESSED):
							toggleRepeat()

			stdscr.refresh()
	except KeyboardInterrupt as ex: return
	finally: p.stop()

if (__name__ == '__main__'):
	logstarted()
	db.load()
	user()
	#if ('xterm' in os.environ['TERM']): os.environ['TERM'] = 'xterm-1002' # mouse movement
	exit(curses.wrapper(main, user()[0]['id']))
else: logimported()

# by Sdore, 2019
