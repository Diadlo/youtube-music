#!/usr/bin/env python

import subprocess
import os
import sys
import re
import json

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
    pattern = re.compile(r'^[0-9]+\.? ?-? ?')
    for c in chapters:
        title = c['title']
        c['title'] = pattern.split(title)[-1]

    return chapters


def parse_description(desc):
    tracks_info = desc.split('\n')
    pattern = re.compile(r'.+ - [0-9]{2}:[0-9]{2}')
    tracks_info = filter(lambda s: pattern.match(s) is not None, tracks_info)
    tracks = [ {} ]
    for track_info in tracks_info:
        name = track_info.split(' - ')[0]
        time = track_info.split(' - ')[1]
        track = {
            'title': t['name'],
            'start_time': time,
        }
        tracks[-1]['end_time'] = time
        tracks.append(track)

    tracks[-1]['end_time'] = time
    tracks = tracks[1:]
    return tracks


def get_tracks(info):
    chapters = info['chapters']
    if chapters is not None:
        return improve_chapters(chapters)

    desc = info['description']
    return parse_description(desc)


def get_creator(info):
    creator = info['creator']
    if creator is not None:
        return creator

    title = info['title']
    return title.split(' - ')[0]


def get_album(info):
    title = info['title']
    return title.split(' - ')[1].replace('/', '_')


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
    tmp_file = 'youtube_music_tmp'
    audio_file = download(url, tmp_file)
    if audio_file is None:
        exit(1)

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
    split_tracks(audio_file, template, creator, album, tracks)
#os.remove(audio_file)
