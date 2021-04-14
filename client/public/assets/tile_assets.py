import requests
import re

base_url = 'https://commons.wikimedia.org/wiki/File:'

filenames = ['MJd3-.svg', 'MJf2-.svg', 'MJf4-.svg', 'MJt5-.svg', 'MJt7-.svg', 'MJt9-.svg', 'MJw2-.svg', 'MJw4-.svg', 'MJw6-.svg', 'MJw8-.svg', 'MJw9-.svg']
# types = ['s', 't', 'w']

# for t in types:
#   for i in range(1, 10):
#     filenames.append(f'MJ{t}{i}-.svg')

# for i in range(1, 4):
#   filenames.append(f'MJd{i}-.svg')

# for i in range(1, 5):
#   filenames.append(f'MJf{i}-.svg')

for fn in filenames:
  response = requests.get(base_url + fn).text

  pattern = r'https:\/\/upload.wikimedia\.org\/wikipedia\/commons\/.\/..\/....-\.svg'
  result = re.search(pattern, response)

  if result:
    src = result.group(0)
    print(src)
    
    img = requests.get(src)

    file = open(fn, "wb+")
    file.write(img.content)
    file.close()
  else:
    print('No match for ' + fn)


