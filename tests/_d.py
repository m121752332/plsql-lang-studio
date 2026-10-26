import sys
sys.path.insert(0, '.')
import langcrypt
p = langcrypt.decrypt(open(r"C:/Program Files/PLSQL Developer 17/Languages/Taiwan.lang", 'rb').read()).decode('utf-8-sig')
L = p.split('\r\n')
for i, l in enumerate(L):
    if l.strip() in ('Default Preferences', 'User Preferences', 'Personal Preferences') or '個人偏好' in l or '預設偏好' in l:
        print(f'--- line {i+1}'); print('\n'.join(f'{j+1}: {L[j]}' for j in range(i-6, i+4)))
