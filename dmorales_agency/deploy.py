import urllib.request, json, base64

TOKEN = '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'
REPO = 'Mr-Q8/dmorales-website'
HEADERS = {
    'Authorization': 'token ' + TOKEN,
    'Content-Type': 'application/json',
    'User-Agent': 'Python'
}

def get_sha(path):
    url = 'https://api.github.com/repos/' + REPO + '/contents/' + path
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())['sha']
    except:
        return None

def upload(path, filepath):
    with open(filepath, 'rb') as f:
        content = base64.b64encode(f.read()).decode()
    sha = get_sha(path)
    data = {'message': 'Update ' + path, 'content': content}
    if sha:
        data['sha'] = sha
    url = 'https://api.github.com/repos/' + REPO + '/contents/' + path
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=HEADERS, method='PUT')
    with urllib.request.urlopen(req) as r:
        result = json.loads(r.read())
        html_url = result['content']['html_url']
        print('OK: ' + path + ' -> ' + html_url)

upload('index.html', 'index.html')
upload('agency.html', 'agency.html')
print('DEPLOY COMPLETO - Vercel actualizara en 30 segundos')
