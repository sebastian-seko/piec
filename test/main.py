
def get_content(path):
    _file = open(path, "r")
    _content = _file.readline()
    _file.close()
    _content = _content.replace('[','').replace(']','').split(',')
    return [ int(p) for p in _content ]

def condition(k_p,phase,content):
    if (k_p+1) % 12 == 0:
        [ print(f'{c:7}',end='|') for c in content ]
        print(f'{phase}\n')
        content = []
    else:
        content.append(f'{phase}')
    return content

content_preview = get_content("/data/message.txt")
content_current = get_content("/data/message2.txt")
content = []
for k_p, p in enumerate(content_preview): 
    if p != content_current[k_p]: 
        content = condition(k_p,f'{p}>{content_current[k_p]}',content)
    else:
        content = condition(k_p,f'{p}',content)
