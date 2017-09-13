#!/usr/bin/python
from __future__ import print_function
import os
import datetime
import argparse
import httplib2

from apiclient import discovery
from apiclient import errors
from oauth2client import client
from oauth2client import tools
from oauth2client.file import Storage


class GoogleDriveFileInfo(object):
    def __init__(self, file_id, file_name, image_metadata):
        self.file_id = file_id
        self.file_name = file_name
        self.image_metadata = image_metadata

    def get_date_taken(self):
        return datetime.datetime.strptime(self.image_metadata['date'], '%Y:%m:%d %H:%M:%S')

    def __str__(self):
        return '{0}.{1}'.format(self.file_id, self.file_name)


class GoogleDriveFolderInfo(object):
    def __init__(self, folder_id, folder_name, file_infos=[], folder_infos=[]):
        """
        :param folder_name: str
        :param file_infos: GoogleDriveFileInfo
        :param folder_infos: GoogleDriveFolderInfo
        """
        self.folder_id = folder_id
        self.folder_name = folder_name
        self.file_infos = file_infos
        self.folder_infos = folder_infos

    def add_file(self, file_info):
        self.file_infos.append(file_info)

    def add_folder(self, folder_info):
        self.folder_infos.append(folder_info)

    def __str__(self):
        out_str = '{0}.{1}\n'.format(self.folder_id, self.folder_name)
        for file_info in self.file_infos:
            out_str += '\t{0}\n'.format(file_info)
        for folder_info in self.folder_infos:
            out_str += '\n{0}'.format(folder_info)
        return out_str


class GoogleDriveClient(object):
    SCOPES = 'https://www.googleapis.com/auth/drive.metadata.readonly'
    CLIENT_SECRET_FILE = 'client_secret.json'
    APPLICATION_NAME = 'Photo Cataloguer'
    service = None

    def __init__(self):
        pass

    def get_directory_info(self, folder_name='root'):
        folder_id = self.__get_folder_id(folder_name)
        folder = GoogleDriveFolderInfo(folder_id, folder_name, [], [])
        self.__traverse_folder(folder_id, folder)
        return folder

    def __get_flags(self):
        try:
            flags = argparse.ArgumentParser(
                parents=[tools.argparser]).parse_args()
        except ImportError:
            flags = None
        return flags

    def __get_credentials(self):
        flags = self.__get_flags()
        home_dir = os.getcwd()
        credential_dir = os.path.join(home_dir, '.credentials')
        if not os.path.exists(credential_dir):
            os.makedirs(credential_dir)
        credential_path = os.path.join(credential_dir, 'photo-cataloguer.json')

        store = Storage(credential_path)
        credentials = store.get()
        if not credentials or credentials.invalid:
            flow = client.flow_from_clientsecrets(
                self.CLIENT_SECRET_FILE, self.SCOPES)
            flow.user_agent = self.APPLICATION_NAME
            credentials = tools.run_flow(flow, store, flags)
        return credentials

    def __get_service(self):
        if self.service is None:
            credentials = self.__get_credentials()
            http = credentials.authorize(httplib2.Http())
            self.service = discovery.build('drive', 'v2', http=http)

        return self.service

    def __get_folder_id(self, name):
        if name == 'root':
            folder_id = 'root'
        else:
            query = "mimeType='application/vnd.google-apps.folder' and title='{0}'".format(
                name)
            service = self.__get_service()
            results = service.files().list(q=query).execute()
            items = results.get('items', [])
            if not items:
                print('No folder found.')
            else:
                folders_count = len(items)
                if folders_count > 1:
                    print('Found more then one folder with "{0}"'.format(
                        folders_count))
            folder_id = items[0]['id'] if items else None
        print('Folder "{0}", {1}'.format(name, folder_id))
        return folder_id

    def __get_item(self, item_id):
        """
        :param item_id: str
        :return: object
        """
        service = self.__get_service()
        item = service.files().get(fileId=item_id).execute()
        print('Item: "{0}", {1}'.format(item['title'], item_id))
        return item

    def __is_folder(self, mime_type):
        return mime_type == 'application/vnd.google-apps.folder'

    def __is_image(self, mime_type):
        return 'image/' in mime_type

    def __traverse_folder(self, folder_id, folder_info):
        """
        :param folder_id: str
        :param folder_info: GoogleDriveFolderInfo
        :return: GoogleDriveFolderInfo
        """
        service = self.__get_service()
        page_token = None
        while True:
            try:
                param = {}
                if page_token:
                    param['pageToken'] = page_token
                children = service.children().list(folderId=folder_id, **param).execute()

                for child in children.get('items', []):
                    item = self.__get_item(child['id'])
                    if self.__is_image(item['mimeType']):
                        folder_info.add_file(GoogleDriveFileInfo(item['id'], item['title'], item['imageMediaMetadata']))
                    else:
                        folder = GoogleDriveFolderInfo(item['id'], item['title'])
                        folder_info.add_folder(folder)
                        self.__traverse_folder(child['id'], folder)
                page_token = children.get('nextPageToken')
                if not page_token:
                    break
            except errors.HttpError:
                print('An error occurred: %s' % errors.HttpError)
                break


if __name__ == '__main__':
    # mobile_photos_path = input('Mobile photos path: ') or 'Google Photos'
    #    target_photos_path = input('Path to move photos: ') or ''
    client = GoogleDriveClient()
    source_directory = client.get_directory_info('TEST')
    target_directory = client.get_directory_info('OUTPUT')

    print(source_directory)
    print(target_directory)
    # files = client.get_folder(mobile_photos_path)
    # print(files)
    # print(mobile_photos_path)
