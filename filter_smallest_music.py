import os
import shutil
import locale


def get_pair(files, f):
    matches = list(filter(lambda x: x.name == f.name and x.path != f.path, files))
    if len(matches) == 0:
        return None
    elif len(matches) == 1:
        return matches[0]
    else:
        raise AssertionError(f'Multiple matches for file {f.path}')


def main():
    locale.setlocale(locale.LC_ALL, '')

    cwd = os.getcwd()
    dirs = []
    files = []
    to_delete = []
    for f in os.listdir(cwd):
        if os.path.isdir(f):
            dirs.append(f)
        else:
            files.append(f)

    for f in files:
        if os.path.splitext(f)[0] in dirs:
            to_delete.append(os.path.join(cwd, f))

    with open('selection.txt', 'w', encoding='utf-8-sig') as o:
        o.write('\n'.join(to_delete))

if __name__ == "__main__":
    main()
