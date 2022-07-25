import os
import re
import subprocess
from subprocess import *
from optparse import OptionParser

def parseChapters(filename):
    chapters = []
    command = [ "ffmpeg", '-i', filename]
    output = ""
    try:
        # ffmpeg requires an output file and so it errors 
        # when it does not get one so we need to capture stderr, 
        # not stdout.
        output = subprocess.check_output(command, stderr=subprocess.STDOUT)
    except CalledProcessError as e:
        output = e.output 

    for line in iter(output.decode('utf-8').splitlines()):
        m = re.match(r".*Chapter #(\d+:\d+): start (\d+\.\d+), end (\d+\.\d+).*", line)
        num = 0 
        if m != None:
            chapters.append({ "name": m.group(1), "start": m.group(2), "end": m.group(3)})
            num += 1
    return chapters

def getChapters():
    parser = OptionParser(usage="usage: %prog [options] filename", version="%prog 1.0")
    parser.add_option("-f", "--file",dest="infile", help="Input File", metavar="FILE")
    (options, args) = parser.parse_args()
    if not options.infile:
        parser.error('Filename required')
    chapters = parseChapters(options.infile)
    fbase, fext = os.path.splitext(options.infile)
    for chap in chapters:
        print("start:" + chap['start'])
        chap['outfile'] = fbase + "-ch-"+ chap['name'].replace(':', '_') + fext
        chap['origfile'] = options.infile
        print(chap['outfile'])
    return chapters

def convertChapters(chapters):
    for chap in chapters:
        print("start:" +    chap['start'])
        print(chap)
        command = [
                "ffmpeg", '-i', chap['origfile'],
                '-vcodec', 'copy',
                '-acodec', 'copy',
                '-ss', chap['start'],
                '-to', chap['end'],
                chap['outfile']]
        output = ""
        try:
            # ffmpeg requires an output file and so it errors 
            # when it does not get one
            output = subprocess.check_output(command, stderr=subprocess.STDOUT)
        except CalledProcessError as e:
            output = e.output
            raise RuntimeError("command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))

if __name__ == '__main__':
    chapters = getChapters()
    convertChapters(chapters)
