#!/usr/bin/env python

import subprocess
import os
import sys
import re
import json
import re

from tempfile import mkstemp

from youtube_dl import YoutubeDL


def download(url, out_name):
    video_file = out_name + '.out'
    ext = 'mp3'
    audio_file = out_name + '.' + ext
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': video_file,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': ext,
            'preferredquality': '192',
        }],
    }
    
    if os.path.exists(audio_file):
        use_it = enter_bool('{} exists, use it?'.format(audio_file))
        if use_it:
            return audio_file

        override = enter_bool('Override?')
        if not override:
            return None

    with YoutubeDL(ydl_opts) as ydl:
        res = ydl.download([url])

    if res != 0:
        return None

    return audio_file


def get_description(url):
    with YoutubeDL() as ydl:
        return ydl.extract_info(url, download = False)


def improve_chapters(chapters):
    # Remove numbers
    pattern = re.compile(r'[0-9]+\.? ?-? ?')
    for c in chapters:
        title = c['title']
        c['title'] = pattern.split(title)[-1]

    return chapters


_TIME_RE = r'([0-9]{1,2}(:[0-9]{2})+)'
_TIME_PATTERN = re.compile(_TIME_RE)

def remove_time(text):
    strings = _TIME_PATTERN.sub('', text)
    return strings.strip()

def get_info(text):
    title = remove_time(text)
    time = re.findall(_TIME_RE, text)
    start_time = time[0]
    if isinstance(start_time, tuple):
        start_time = start_time[0]

    end_time = None
    if len(time) > 1:
        end_time = time[1]
        if isinstance(end_time, tuple):
            end_time = end_time[0]

    return (title, start_time, end_time)

def get_duration(filename):
    ffprobe = subprocess.Popen(['ffprobe', '-i', filename],
            stderr=subprocess.PIPE)
    out, err = ffprobe.communicate();
    text = err.decode('utf8')
    res = re.search(r'(?<=Duration: )[0-9:.]+', text).group(0)
    return res

def parse_description(desc):
    tracks_info = desc.split('\n')
    tracks_info = filter(lambda s: _TIME_PATTERN.findall(s) != [], tracks_info)
    tracks = []
    for track_info in tracks_info:
        title, start, end = get_info(track_info)
        track = {
            'title': title,
            'start_time': start,
            'end_time': end,
        }
        
        if len(tracks) > 0 and tracks[-1]['end_time'] is None:
            tracks[-1]['end_time'] = start

        tracks.append(track)

    if len(tracks) > 0 and tracks[-1]['end_time'] is None:
        tracks[-1]['end_time'] = start

    return tracks


def get_tracks(info):
    chapters = info['chapters']
    chapters = None
    if chapters is None:
        print('\nChapters not found. Trying parse desription')
        desc = info['description']
        chapters = parse_description(desc)

    return improve_chapters(chapters)


def get_creator(info):
    creator = info['creator']
    if creator is not None:
        return creator

    title = info['title']
    return title.split(' - ')[0]


def get_album(info):
    title = info['title']
    a = title.split(' - ')
    if len(a) == 1:
        return title

    return a[1].replace('/', '_')


def enter_bool(prompt='', default=True):
    text = ' [Y/n] ' if default else ' [y/N] '
    print(prompt + text, end='', flush=True)
    res = sys.stdin.readline().strip()
    if res == '':
        return default

    not_default = 'N' if default else 'Y'
    if res[0].upper() == not_default:
        return not default

    return default


def enter_default(prompt, default):
    if enter_bool('\n{}: {}?'.format(prompt, default)):
        return default

    print('Enter new value: ', end='', flush=True)
    return sys.stdin.readline().strip()


def enter_tracks(tracks):
    titles = []
    (idk, tmp) = mkstemp()
    print('\nTracks:')
    with open(tmp, 'w') as f:
        for t in tracks:
            print(t['title'])
            f.write(t['title'] + '\n')

    if enter_bool('Is it correct?'):
        os.remove(tmp)
        return tracks

    os.system('${EDITOR:-vim} ' + tmp)
    with open(tmp) as f:
        titles = f.readlines()

    for (track, title) in zip(tracks, titles):
        track['title'] = title[:-1]

    os.remove(tmp)
    return tracks


def update_template(template, creator, album, last_id):
    id_len = len(str(last_id))
    id_template = '{{id:0{l}d}}'.format(l = id_len)
    track_template = '{track}'
    return template.format(
            creator = creator,
            album = album,
            id = id_template,
            track = track_template)


def split_tracks(audio_file, template, creator, album, tracks):
    i = 1
    for t in tracks:
        name = template.format(id = i, track = t['title'])
        start = str(t['start_time'])
        end = str(t['end_time'])
        print(name)
        p = subprocess.Popen(['ffmpeg', '-i', audio_file, '-ss', start, '-to', end, 
                '-c', 'copy', name], stdout=subprocess.PIPE)
        p.communicate()
        i += 1


if __name__ == "__main__":
    argc = len(sys.argv)
    if argc != 2:
        print('Usage: {} <url>'.format(sys.argv[0]))
        exit(0)

    url = sys.argv[1]
    info = get_description(url)

    creator = get_creator(info)
    creator = enter_default('Creator', creator)

    album = get_album(info)
    album = enter_default('Album', album)

    tracks = get_tracks(info)
    tracks = enter_tracks(tracks)
    
    template = '{creator}/{album}/{id}. {track}.mp3'
    template = update_template(template, creator, album, len(tracks))
    path = os.path.dirname(template)
    os.makedirs(path, exist_ok = True)

    tmp_file = 'youtube_music_tmp'
    audio_file = download(url, tmp_file)
    if audio_file is None:
        exit(1)

    tracks[-1]['end_time'] = get_duration(audio_file)
    split_tracks(audio_file, template, creator, album, tracks)
