import imaplib
import email
import json
import base64
import os
from os.path import dirname, abspath

#parse config
config = json.load(open(abspath(dirname(__file__))+"/Config.json"))
user = config['mail']['login']
settings = config['mail']['settings']
fileconfig = config['files']

#img filepath
path_to_dir = abspath(dirname(__file__))
filepath = path_to_dir+'/'+fileconfig['path']
max_foldersize = fileconfig['max_foldersize']
mail_folder = settings['folder']


#create IMAP with SSL
imap = imaplib.IMAP4_SSL(settings['imap'], settings['port'])

#auth
imap.login(user['mail'], user['password'])

status, messages = imap.select(mail_folder)

type, data = imap.search(None, 'UNSEEN')
mail_ids = data [0]
id_list = mail_ids.split()

for num in data[0].split():
    typ, data = imap.fetch(num, '(RFC822)' )
    raw_mail = data[0][1]
    
    #converts byte literal to string
    email_message = email.message_from_string(raw_mail.decode('utf-8'))
    
    #download attachements
    for part in email_message.walk():
        #..
        if part.get_content_maintype() == 'multipart':
            continue
        if part.get('Content-Disposition') is None:
            continue
        fileName = part.get_filename()
            
        if bool(fileName):
            filePath = os.path.join(filepath, fileName)
            if not os.path.isfile(filePath) and not fileName.endswith(".txt"):
                fp = open(filePath, 'wb')
                fp.write(part.get_payload(decode=True))
                fp.close
            
            subject = str(email_message).split("Subject: ", 1)[1].split("\nTo:", 1)[0]
            print('Downloaded "{fileName}" from email to"{path}".'.format(fileName=fileName, path=filepath))
            
            #if more than X files, delete oldest one
            list_of_files=os.listdir(filepath)
            full_path = [filepath+"{0}".format(x) for x in list_of_files]
            
            if len(list_of_files) > max_foldersize:
                os.remove(min(full_path, key=os.path.getctime))
                print('Exceeded max_foldersize of ' + str(max_foldersize) + ', deleting oldest file.')
        
    
    imap.store(num, '+FLAGS', '\Deleted')

imap.close()
imap.logout()

print('Done...')
