import argparse
import os
import sys
import re

try:
    from editorconfig import get_properties, EditorConfigError
    E_CONF = (get_properties, EditorConfigError)
except Exception as e:
    print("Failed to import editorconfig module, '.editorconfig' files would be ignored", file=sys.stderr)
    E_CONF = None


VERSION = "1.1a.0"
VERSION_HISTORY = {
    "1.1a.0": {
        "Release Notes": "Bugfixes, new options: `--all`, `--realign`",
        "Bugfixes":  [
            "Relative path in path to sources could affect output path",
            "Absence of editorconfig module was critical error",
        ],
        "Breaking changes": [
            "--suggest-config doesn't takes args anymore, now it's just toggle"
        ],
    },
    "1.0.0": {
        "Release Notes": "Initial release"
    }
}


ENCODINGS = ('utf-8', ) # Fallback encodings if nothing is specified
_LE = {'lf' : '\n', 'crlf'  : '\r\n', 'cr' : '\r', }


def fix_spaces(line, tab_width, trim):
    result = ""
    spaces = ""
    pos = 0
    for i in range(0, len(line)):
        if line[i] != "\t":
            if line[i] == " ":
                spaces += " "
            else:
                if not trim or line[i] not in ("\r", "\n"):
                    if len(spaces) > 0:
                        result += spaces
                        pos += len(spaces)
                spaces = ""
                result += line[i]
                pos += 1
        else:
            t = tab_width - (pos + len(spaces)) % tab_width
            spaces += " " * t
    return result


def fix_tabs(line, tab_width, trim):
    result = ""
    spaces = ""
    tabs = ""
    pos = 0
    for i in range(0, len(line)):
        if line[i] == "\t":
            tabs += "\t"
            t = tab_width - pos % tab_width
            pos += t
            spaces = ""
        elif line[i] != " ":
            if not trim or line[i] not in ("\r", "\n"):
                if len(tabs) > 0:
                    result += tabs
                if len(spaces) > 0:
                    result += spaces
                    pos += len(spaces)
            tabs = ""
            spaces = ""
            result += line[i]
            pos += 1
        else:
            if spaces == "" and tabs == "" and line[i+1] not in (" ", "\t", "\r", "\n"):
                # Single space in between - just post it
                result += " "
                pos += 1
                continue
            spaces += " "
            cp = pos + len(spaces)
            if cp % tab_width == 0:
                tabs += "\t"
                pos += len(spaces)
                spaces = ""
    return result


def realign_text(line, use_tabs, tab_width):
    chunks_map = []
    spaces = 0
    space_chars = 0
    tabs = False
    pos = 0

    # Detect chunks of text
    for i in range(0, len(line)):
        if line[i] == "\t":
            tabs = True
            spaces += tab_width - pos % tab_width
            pos += tab_width - pos % tab_width
            space_chars += 1
        elif line[i] == " ":
            spaces += 1
            pos += 1
            space_chars += 1
        else:
            if tabs or len(chunks_map) == 0 or spaces >= tab_width:
                if len(chunks_map) > 0:     # TODO: try to increase threshold ?
                    prev_chunk_length = i - space_chars - chunks_map[-1]['origin']
                    chunks_map[-1]['after']  = spaces
                    chunks_map[-1]['value']  = line[
                        chunks_map[-1]['origin'] :
                        chunks_map[-1]['origin'] + prev_chunk_length
                    ]
                chunks_map.append({
                    # NOTE: some of those fields are only to check under debug that things works properly
                    'origin': i,            # Chunk start within line
                    'size'  : None,         # Chunk size in display chars (where size of tab char == tab_width)
                    'before': spaces,       # Display whitespaces before chunk
                    'after' : 0,            # Display whitespaces after chunk
                    'target': pos,          # Chunk start within result in display chars
                    'move_right': False,    # Chunk should be moved to the right
                    'value' : None          # All chunk's line chars
                })
            spaces = 0
            space_chars = 0
            tabs = False
            pos += 1

    assert len(chunks_map) != 0, "Something went wrong" # NOTE: every line should contain at least EOL sequence
                                                        #       so chunks map can't be empty
    assert spaces == 0, "Something went wrong"          # NOTE: at this stage only chunk with EOL sequence can be,
    assert space_chars == 0, "Something went wrong"     #       so spaces and space_chars should be 0

    chunks_map[-1]['value']  = line[chunks_map[-1]['origin'] : ]

    # Calculate chunks sizes:
    for chunk in chunks_map:
        chunk['size'] = 0
        for char in chunk['value']:
            if char == '\t':
                # NOTE: tab always splits text into chunks, but in case if this behavior would change,
                # following code should be used
                chunk['size'] += tab_width - chunk['size'] % tab_width
            else:
                chunk['size'] += 1

    # Align chunks
    a=1 # TODO: remove this line after debug
    for i in range(0, len(chunks_map)):
        prev_chunk = None
        next_chunk = None
        realign = False
        chunk = chunks_map[i]
        if i > 0:
            prev_chunk = chunks_map[i-1]
        if i < len(chunks_map)-1:
            next_chunk = chunks_map[i+1]
        pos = chunk['target']   # Current chunk's position on display
        offs = pos % tab_width  # Chunk's misalignment
        realign = offs != 0
        if prev_chunk is None:
            # It's safe and reasonable to move first chunk to the left
            if  realign:
                chunk['target'] = pos - offs
        else:
            # Try to move left if unaligned. Leave at least 'tab_width' spaces from each side
            if realign:
                if not chunk['move_right']:
                    t = pos - offs
                    if t - prev_chunk['target'] < tab_width + prev_chunk['size']:
                        chunk['move_right'] = True
                    else:
                        chunk['target'] = t

            # If need to move right then do it
            if chunk['move_right']:
                t = (prev_chunk['target'] + prev_chunk['size'] + tab_width + tab_width-1) // tab_width * tab_width
                if t >= chunk['target']:
                    chunk['target'] = t
                else:
                    if offs > 0:
                        assert False, "Something went wrong"    # TODO: probably we shouldn't be here at all
                        chunk['target'] = pos + tab_width - offs

                # Check if it's required to move next chunk to the right
                if next_chunk is not None:
                    if (t + chunk['size'] + tab_width + tab_width-1) // tab_width * tab_width < next_chunk['target']:
                        next_chunk['move_right'] = True


    # Put chunks into resulting string
    result = ""
    pos = 0
    for chunk in chunks_map:
        assert chunk['target'] >= pos, "Something went wrong"
        while pos < chunk['target']:
            if use_tabs:
                result += "\t"
                pos += tab_width - pos % tab_width
            else:
                dp = (chunk['target'] - pos)
                result += " " * dp
                pos += dp
        assert chunk['target'] == pos, "Something went wrong"
        result += chunk['value']
        pos += chunk['size']    # It's OK to do like this since sizes were calculated for aligned chunks

    return result


def fix_indents_in_file(
        file_path, output_path=None,
        encodings=None, tab_width=None, use_tabs=None, trim=None, line_endings=None, realign=False, all_files=False):
    lines = None
    last_error = None
    encoding = None
    suggest = {}
    no_last_line_break = False

    if not os.path.exists(file_path):
        raise ValueError(f"File '{file_path}' not found!")
    elif not os.path.isfile(file_path):
        raise ValueError(f"Path '{file_path}' should point to file!")

    if E_CONF is not None:
        try:
            options = E_CONF[0](file_path)
        except E_CONF[1]:
            options = {}
    else:
        options = {}

    if E_CONF is not None and not all_files and len(options) == 0:
        return suggest

    if 'charset' in options:
        encoding = options['charset']
        if encodings is None:
            encodings = ENCODINGS
        encodings = (encoding, *encodings)

    if encodings is None:
        encodings = ENCODINGS

    for en in encodings:
        f = None
        try:
            f = open(file_path, "rb")
            text = f.read().decode(encoding=en)
            lines = None
            for line_break in ('\r\n', '\n', '\r'):
                if line_break in text:
                    lines = [l + '\n' for l in text.split(line_break)]
                    break
            if lines is None:
                line_break = '\n'
                lines = [text + '\n']
            no_last_line_break = text[-len(line_break):] != line_break
            f.close()
            if encoding is None:
                encoding = en
                suggest['charset'] = en
        except Exception as e:
            if f is not None:
                f.close()
            last_error = e
            continue
        break

    if lines is None:
        raise last_error

    if use_tabs is None:
        if 'indent_style' in options:
            use_tabs = options['indent_style'] == 'tab'

    if use_tabs is None:
        tabs = 0
        spaces = 0
        for l in lines:
            if l[:1] == "\t":
                tabs += 1
                continue
            if l[:1] == " ":
                spaces += 1
        use_tabs = tabs > spaces
        suggest['indent_style'] = ('space', 'tab')[use_tabs]

    if tab_width is None:
        if 'indent_size' in options:
            try:
                tab_width = int(options['indent_size'])
            except ValueError:
                pass
    if tab_width is None:
        tab_width = 4
        suggest['indent_size'] = 4

    if trim is None:
        if 'trim_trailing_whitespace' in options:
            trim = options['trim_trailing_whitespace'] == 'true'
    if trim is None:
            trim = True
            suggest['trim_trailing_whitespace'] = 'true'

    if line_endings is None:
        if 'end_of_line' in options:
            line_endings = options['end_of_line']

    if line_endings is not None:
        line_endings = _LE[line_endings]

    result = []
    for l in lines:
        if use_tabs:
            o_l = fix_tabs(l, tab_width, trim)
        else:
            o_l = fix_spaces(l, tab_width, trim)
        result.append(o_l)

    if realign:
        to_realign = result
        result = []
        # TODO: try to analyze adjacent lines and get 2D chunks
        for l in to_realign:
            o_l = realign_text(l, use_tabs, tab_width)
            result.append(o_l)

    if output_path is not None:
        os.makedirs(os.path.split(output_path)[0], exist_ok=True)
    else:
        output_path = file_path
    with open(output_path, "wb") as f:
        if len(text) > 0:
            if line_endings is not None:
                line_break = line_endings
            o_text = line_break.join([l[:-1] for l in result])
            if not no_last_line_break:
                o_text += line_break
            f.write(o_text.encode(encoding))

    return suggest


def _skip(file_path, include, exclude):
    skip = False

    if include is not None:
        skip = True
        for ptn in include:
            m = re.match(ptn, file_path.lower())
            if m is not None:
                skip = False
                break

    if not skip and exclude is not None:
        for ptn in exclude:
            m = re.match(ptn, file_path.lower())
            if m is not None:
                skip = True
                break

    return skip


def _best_suggestions(vals):
    return {}  # TODO: suggestions


def fix_indents_in_path(
        path, output_path=None, encodings=None, tab_width=None, use_tabs=None, trim=None, line_endings=None,
        include=None, exclude=None, suggest=False, realign=False, all_files=False):
    if not os.path.exists(path):
        raise ValueError(f"Path {os.path.abspath(path)} doesn't exists!")

    if tab_width is not None \
    or use_tabs is not None \
    or trim is not None \
    or line_endings is not None:
        all_files = True

    if os.path.isdir(path):
        fo = None
        for root, _, files in os.walk(path):
            suggestions = {}
            if any(hp in root for hp in ("/.", "\\.")):
                continue
            for f in files:
                if f[:1] == ".":
                    continue
                m = re.match(r'^.*?\.([^.]+)$', f)
                if m is not None:
                    file_ext = m.groups()[0]
                else:
                    file_ext = ''
                if file_ext not in suggestions:
                    suggestions[file_ext] = []
                if _skip(os.path.join(root, f), include, exclude):
                    suggestions[file_ext].append({})
                    continue
                if output_path is not None:
                    if root == path:
                        fo = os.path.abspath(os.path.join(output_path, f))
                    else:
                        fo = os.path.abspath(os.path.join(output_path, root[len(path)+1:], f))
                suggestions[file_ext].append(
                    fix_indents_in_file(
                        os.path.abspath(os.path.join(root, f)), fo, encodings, tab_width, use_tabs, trim, line_endings,
                        realign, all_files)
                )
            if suggest:
                ecp = os.path.join(root, '.editorconfig')
                if os.path.exists(ecp):
                    # TODO: update existing file
                    continue
                ecl = []
                for k, v in suggestions.items():
                    bs = _best_suggestions(v)
                    if len(bs) > 0:
                        ecl.append("")
                        ecl.append(f"[*.{k}]")
                        for pk, pv in bs.items():
                            ecl.append(f"{pk} = {pv}")
                if len(ecl) > 0:
                    with open(ecp, "w", encoding='utf-8') as ecf:
                        ecf.writelines(ecl)
    else:
        if not any(hp in path for hp in ("/.", "\\.")) \
        and not _skip(path, include, exclude):
            if output_path is not None:
                output_path = os.path.abspath(output_path)
            fix_indents_in_file(os.path.abspath(path), output_path, encodings, tab_width, use_tabs, trim, line_endings)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog = "python unifile.py",
        description= "Fix indentation chars in file or files within path according to specified rules,"
                     " trim trailing whitespaces, change files encodings and line endings as necessary."
                     " If rules aren't specified via CLI then will try to use '.editorconfig' files or fallback to defaults"
                     f" Version: {VERSION}",
        epilog = "That's all, folks!",
    )

    parser.add_argument('path', help='Path to file or folder to fix')
    parser.add_argument('-o', '--output', required=False, dest='output_path', default=None,
                        help='Output path. If omitted then result is saved in place')
    parser.add_argument('-s', '--tab-size', required=False, dest='tab_width', type=int, default=None,
                        help='Tab size. Fallbacks to 4')
    parser.add_argument('-c', '--indent-char', required=False, dest='indent_char', default='auto',
                        choices=['auto', 'space', 'tab'],
                        help='Indentation character.'
                        ' Fallbacks to majority of whitespaces used as first line character within each file')
    parser.add_argument('-t', '--trim', required=False, dest='trim', default='auto',
                        choices=['auto', 'true', 'false'],
                        help='Trim trailing whitespaces. Fallbacks to true')
    parser.add_argument('-l', '--line-endings', required=False, dest='line_endings', default='auto',
                        choices=['auto', 'lf', 'crlf', 'cr'],
                        help='Set line endings. Fallbacks to don\'t change')
    parser.add_argument('-e', '--encoding', required=False, dest='encodings', action='append', default=None,
                        help='Encoding to open files with. Multiple encodings may be provided in order of precedence.'
                            f' Fallbacks to {", ".join(ENCODINGS)}')
    parser.add_argument('-r', '--realign', required=False, dest='realign', action='store_true',
                        help='Realign text so it start on tab-stops.')
    parser.add_argument('-a', '--all', required=False, dest='all_files', action='store_true',
                        help='If no explicit rules defined, then by default scripts processes only files'
                             ' that are mentioned in editorconfig. This option enforces to process all files. '
                             ' Include and Exclude options are still applicable.')
    parser.add_argument('-i', '--include', required=False, dest='include', action='append', default=None,
                        help='Pattern to include files for processing. Multiple patterns may be provided.'
                             ' If omitted then all are included by default'
                             ' (files and folders starting with \'.\' aka \'hidden\' are always skipped)')
    parser.add_argument('-x', '--exclude', required=False, dest='exclude', action='append', default=None,
                        help='Pattern to exclude files from processing. Multiple patterns may be provided.'
                             ' If omitted then no files excluded (except \'hidden\').'
                             ' If specified then takes precedence over include')
    parser.add_argument('--suggest-config', required=False, dest='suggest', action='store_true',
                        help="TODO: Fill-in missing '.editorconfig' file according to existing files (on per-folder basis)")
    args = parser.parse_args()
    fix_indents_in_path(
        args.path,
        args.output_path,
        args.encodings,
        args.tab_width,
        [args.indent_char == 'tab', None][args.indent_char == 'auto'],
        [args.trim == 'true', None][args.trim == 'auto'],
        [args.line_endings, None][args.line_endings == 'auto'],
        args.include,
        args.exclude,
        args.suggest,
        args.realign,
        args.all_files,
    )
