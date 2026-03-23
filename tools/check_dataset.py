import json
from collections import Counter

data = json.load(open('tools/annotations/merged.json'))

origens = Counter()
for img in data['images']:
    nome = img['file_name']
    if 'YTDown' in nome or 'YouTube' in nome:
        origens['YouTube'] += 1
    elif 'pasqua' in nome.lower():
        origens['Pasqua'] += 1
    else:
        origens['Outros'] += 1

total = len(data['images'])
for k, v in sorted(origens.items(), key=lambda x: -x[1]):
    print(f"{k:20s}: {v} imagens ({v/total*100:.1f}%)")
print(f"Total: {total}")

# Lista todos os prefixos únicos de nomes de arquivo
print("\n--- Origens únicas ---")
prefixos = Counter()
for img in data['images']:
    nome = img['file_name'].split('_f0')[0]  # remove o sufixo do frame
    prefixos[nome] += 1
for k, v in sorted(prefixos.items(), key=lambda x: -x[1]):
    print(f"  {v:4d}x  {k}")
