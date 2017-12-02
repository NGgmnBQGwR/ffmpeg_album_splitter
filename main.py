# encoding:utf-8
"""
Simple ffmpeg wrapper to split single file musical albums
into separate tracks, using silence as track separator.
"""

import os
import sys
import math
import shlex
import subprocess
from collections import namedtuple

FFMPEG_GET_INTERVAL_COMMAND = r'''ffmpeg -i "{input}" -af silencedetect=noise=-30dB:d=0.25 -f null -'''
FFMPEG_CUT_TRACK = r'''ffmpeg -i "{input}" -acodec copy -ss {start} -to {end} "{output}"'''

# any silence longer than this will emit a warning
MAX_SILENCE_LENGTH = 5
# any track below this will emit a warning
MIN_TRACK_LENGTH = 30


Interval = namedtuple('Interval', ['start', 'end', 'duration'])


def timestamp_to_seconds(timestamp):
    """
    Given a timestamp in form of "00:00:00.00", returns its time in seconds.
    """
    parts = timestamp.split(':')

    seconds = 0
    if len(parts) >= 1:
        seconds = float(parts[-1])

    minutes = 0
    if len(parts) >= 2:
        minutes = int(parts[-2])

    hours = 0
    if len(parts) >= 3:
        hours = int(parts[-3])

    return seconds + minutes*60 + hours*60*60


def format_time_from_seconds(input_seconds):
    """
    Given an amount of seconds, returns a timestamp in form of "00:00:00.00".
    """
    hours = int(input_seconds / (60 * 60))
    minutes = int(input_seconds / 60) % 60
    seconds = int(input_seconds % 60)
    milliseconds = int(math.modf(input_seconds)[0]*100)

    return "{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:02}".format(
        hours=hours,
        minutes=minutes,
        seconds=seconds,
        milliseconds=milliseconds,
    )


def get_silence_data(input_filename):
    """
    Get information about silence in given audio file.
    Caches and reuses results to avoid analysing same file twice to save time.
    """
    output_filename = '_output_{}_{}.txt'.format(
        os.path.basename(input_filename),
        os.path.getsize(input_filename),
    )
    if os.path.exists(output_filename):
        with open(output_filename, 'rb') as inp:
            return inp.read()

    command_name = FFMPEG_GET_INTERVAL_COMMAND.format(input=input_filename)
    command = subprocess.Popen(
        shlex.split(command_name),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    print 'Calling ffmpeg to get silence data...'
    output_out, output_err = command.communicate()

    # ffmpeg writes everything to the stderr, which is why we're ignoring stdout
    with open(output_filename, 'wb') as out:
        out.write(output_err)

    return output_err


def get_sound_boundaries(silence_data):
    """
    Find sound boundaries from ffmpeg output.
    """
    interval_data = []
    file_start = None
    file_end = None

    # transform lines taken from ffmpeg output in form of
    #    [silencedetect @ 0000000001ca7b40] silence_end: 6.7735 | silence_duration: 0.27
    #    [silencedetect @ 0000000001ca7b40] silence_start: 7.0035
    # into a list of namedtuples with 1:1 mapping - every tuple corresponds to a single line
    for line in silence_data.splitlines():
        line = line.strip()
        if line.startswith('[silencedetect'):
            if 'silence_start' in line:
                start = float(line.split(':')[1])
                interval = Interval(start, None, None)
                interval_data.append(interval)
            elif 'silence_end' in line:
                temp_split = line.split('|')
                end = float(temp_split[0].split(':')[1])
                duration = float(temp_split[1].split(':')[1])
                interval = Interval(None, end=end, duration=duration)
                interval_data.append(interval)
            else:
                raise AssertionError('Unknown silencedetect line: "{}"'.format(line))
        elif line.startswith('Duration'):
            temp_split = line.split(',')
            temp_duration = temp_split[0]
            temp_start = temp_split[1]
            file_end = timestamp_to_seconds(temp_duration.split(' ')[1])
            file_start = float(temp_start.split(':')[1])

    if file_start is None or file_end is None:
        raise AssertionError('start or end not found: {}/{}'.format(start, end))

    # transforms list of namedtuples into a list of silence boundaries:
    # [(0, start_of_next_silence), (end_of_previous_silence, start_of_next_silence), ..., (end_of_previous_silence, end_of_file)]
    sound_boundaries = []
    previous_silence_start = None
    previous_silence_end = None
    interval_data_len = len(interval_data)

    for index, interval in enumerate(interval_data):
        if index == 0:
            # for first track, we take everything from 0 to first silence start
            # thus, we assume that first encountered silence marker is "silence start"
            assert interval.start is not None
            sound_boundaries.append((0, interval.start))
        elif index == interval_data_len-1:
            # for last track, we take everything from last "silence end" to the end of the file
            sound_boundaries.append((previous_silence_end, file_end))
        else:
            # otherwise, we take everything between last silence end and new silence start
            if interval.start:
                sound_boundaries.append((previous_silence_end, interval.start))

        if interval.start:
            previous_silence_start = interval.start
        elif interval.end:
            previous_silence_end = interval.end

    return sound_boundaries


def find_tracks(sound_boundaries, gap_multiplier=1):
    """
    Accepts list of sound boundaries.
    Tries to apply a simple heuristic to determine how to group sounds into tracks.
    Return list of tracks start/end markers.
    """
    previous_end = None

    average_midsound_silence = sum([x[1][0] - x[0][1] for x in zip(sound_boundaries, sound_boundaries[1:])]) / len(sound_boundaries)
    print 'Using pause of {} seconds to separate tracks.'.format(average_midsound_silence * gap_multiplier)

    track_boundaries = []
    track_start = sound_boundaries[0][0]
    track_end = sound_boundaries[0][1]

    entry = "Track {index:02} [{duration}] {start} - {finish} ({starts} - {finishs}){warnings}"
    for index, sound_boundary in enumerate(sound_boundaries):
        track_gap = sound_boundary[0] - track_end
        if track_gap > average_midsound_silence * gap_multiplier:
            track_boundaries.append((track_start, track_end + (track_gap/2)))
            track_start = sound_boundary[0] - (track_gap/2)
        track_end = sound_boundary[1]

    if not track_boundaries:
        return

    # insert last track if it didn't fit above
    if track_boundaries[-1][1] < track_end:
        track_boundaries.append((track_boundaries[-1][1], track_end))

    return track_boundaries


def print_tracks(track_boundaries):
    """
    Print detected tracks in a human-friendly format.
    """
    if not track_boundaries:
        return
    entry = "Track {index:02} [{duration}] {start} - {finish} ({starts} - {finishs})"
    for index, track in enumerate(track_boundaries):
        print entry.format(
            index=index,
            duration=format_time_from_seconds(track[1]-track[0])[3:],
            start=format_time_from_seconds(track[0]),
            finish=format_time_from_seconds(track[1]),
            starts=track[0],
            finishs=track[1],
        )

    print 'Total tracks: {}'.format(len(track_boundaries))


def confirm(text=None):
    """
    Asks the user for confirmation
    """
    while True:
        valid = raw_input(text or 'Is this ok?\n').strip()
        if valid.lower() in ['y', 'ye', 'yes']:
            return True
        else:
            return False


def split_file_into_tracks(input_filename, track_boundaries):
    """
    Splits input audio file into separate tracks.
    """
    output_folder_name, extension = os.path.splitext(os.path.basename(input_filename))
    output_folder = os.path.join(os.getcwd(), output_folder_name)
    if not os.path.exists(output_folder):
        os.mkdir(output_folder)

    output_files = os.listdir(output_folder)
    files_count = len(output_files)
    if files_count:
        clear_folder = confirm("Folder '{}' contains {} files - delete them?".format(output_folder_name, files_count))
        if clear_folder:
            for file_ in output_files:
                os.remove(os.path.join(output_folder, file_))

    for index, track in enumerate(track_boundaries):
        filename = "Track{:02}".format(index)

        command_name = FFMPEG_CUT_TRACK.format(
            input=input_filename,
            output=os.path.join(output_folder, filename)+extension,
            start=track[0],
            end=track[1],
        )
        print 'Processing {}...'.format(filename)
        result = subprocess.check_call(shlex.split(command_name), stderr=subprocess.PIPE)


def main():
    if len(sys.argv) < 2:
        print 'Need a filename as argument'
        return

    input_filename = sys.argv[1]
    if not os.path.exists(input_filename):
        print 'File not found: "{}"'.format(input_filename)
        return

    silence_data = get_silence_data(input_filename)
    sound_data = get_sound_boundaries(silence_data)

    for mult in [1, 0.5, 1.5, 0.25, 2, 3, 4, 5]:
        tracks_data = find_tracks(sound_data, mult)
        print_tracks(tracks_data)
        is_ok = confirm()
        if is_ok:
            break
    if not is_ok:
        return

    split_file_into_tracks(input_filename, tracks_data)
    raw_input('Finished.')


if __name__ == "__main__":
    main()