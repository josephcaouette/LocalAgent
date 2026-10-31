import fnmatch
def match(pattern, text):
    return fnmatch.fnmatchcase(text, pattern)
