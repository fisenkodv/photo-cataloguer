#!/usr/bin/python
from __future__ import print_function
import os
import argparse
import httplib2
import dateutil.parser

from apiclient import discovery
from apiclient import errors
from oauth2client import client
from oauth2client import tools
from oauth2client.file import Storage


class GoogleDriveFileInfo(object):
    def __init__(self, file_id, file_name, metadata):
        self.file_id = file_id
        self.file_name = file_name
        self.metadata = metadata

    def can_be_moved(self):
        return 'date' in self.metadata

    def get_date_taken(self):
        return dateutil.parser.parse(self.metadata['date'])

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

    def get_files(self, recursive=False):
        """
        :param recursive: boolean
        """
        file_infos = []
        file_infos.extend(self.file_infos)
        if recursive:
            for folder_info in self.folder_infos:
                file_infos.extend(folder_info.get_files(True))
        return file_infos

    def get_folder(self, folder_name):
        found_folders = [folder_info for folder_info in self.folder_infos if folder_info.folder_name == folder_name]
        return found_folders[0] if len(found_folders) == 1 else None

    def file_exists(self, file_info):
        """
        :param file_info: GoogleDriveFileInfo
        :return: bool
        """
        file_infos = [x for x in self.get_files(False) if x.file_name == file_info.file_name]
        return True if len(file_infos) != 0 else False

    def __str__(self):
        out_str = '{0}.{1}\n'.format(self.folder_id, self.folder_name)
        for file_info in self.file_infos:
            out_str += '\t{0}\n'.format(file_info)
        for folder_info in self.folder_infos:
            out_str += '\n{0}'.format(folder_info)
        return out_str


class GoogleDriveClient(object):
    SCOPES = 'https://www.googleapis.com/auth/drive'
    CLIENT_SECRET_FILE = 'client_secret.json'
    APPLICATION_NAME = 'Photo Cataloguer'
    service = None

    def __init__(self):
        pass

    def get_folder_info(self, directory_name='root'):
        folder_id = self.__get_folder_id(directory_name)
        folder = GoogleDriveFolderInfo(folder_id, directory_name, [], [])
        self.__traverse_folder(folder_id, folder)
        return folder

    def create_folder(self, folder_name, parent_folder_id):
        file_metadata = {
            'title': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [{'id': parent_folder_id}]
        }
        service = self.__get_service()
        new_folder = service.files().insert(body=file_metadata, fields='id').execute()
        folder_info = GoogleDriveFolderInfo(new_folder['id'], folder_name, [], [])
        return folder_info

    def move_file(self, parent_folder_id, file_id):
        service = self.__get_service()
        existing_file = service.files().get(fileId=file_id, fields='parents').execute()
        previous_parents = ",".join([parent["id"] for parent in existing_file.get('parents')])
        # Move the existing_file to the new folder
        existing_file = service.files().update(fileId=file_id,
                                               addParents=parent_folder_id,
                                               removeParents=previous_parents,
                                               fields='id, parents').execute()

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

    def __is_supported_media(self, mime_type):
        return 'image/' in mime_type or 'video/' in mime_type

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
                    if self.__is_supported_media(item['mimeType']):
                        metadata = {'date': item['createdDate']};
                        if 'imageMediaMetadata' in item:
                            metadata = dict(metadata.items() + item['imageMediaMetadata'].items())
                        folder_info.add_file(GoogleDriveFileInfo(item['id'], item['title'], metadata))
                    else:
                        folder = GoogleDriveFolderInfo(item['id'], item['title'], [], [])
                        folder_info.add_folder(folder)
                        self.__traverse_folder(child['id'], folder)
                page_token = children.get('nextPageToken')
                if not page_token:
                    break
            except errors.HttpError:
                print('An error occurred: %s' % errors.HttpError)
                break


class Cataloguer(object):
    def __init__(self, source_photos_path, target_photos_path):
        self.source_photos_path = source_photos_path
        self.target_photos_path = target_photos_path
        self.client = GoogleDriveClient()

    def catalogue(self):
        source_directory = self.client.get_folder_info(self.source_photos_path)
        target_directory = self.client.get_folder_info(self.target_photos_path)
        source_files = source_directory.get_files(True)

        for file_info in source_files:
            if file_info.can_be_moved() is False:
                continue
            date_taken = file_info.get_date_taken()
            print('{0}/{1}/{2}'.format(
                str(date_taken.year).zfill(4),
                str(date_taken.month).zfill(2),
                str(date_taken.day).zfill(2)))

            year_folder = self.__get_folder(target_directory, str(date_taken.year).zfill(4))
            month_folder = self.__get_folder(year_folder, str(date_taken.month).zfill(2))
            day_folder = self.__get_folder(month_folder, str(date_taken.day).zfill(2))
            if day_folder.file_exists(file_info):
                print('File "{0}" already exists'.format(file_info))
            else:
                print('Move "{0}"'.format(file_info))
                self.client.move_file(day_folder.folder_id, file_info.file_id)

    def __get_folder(self, parent_folder, folder_name):
        """
        :param parent_folder: GoogleDriveFolderInfo
        :param folder_name: str
        :return: GoogleDriveFolderInfo
        """
        folder = parent_folder.get_folder(folder_name)
        if folder is None:
            print('Create folder "{0}"'.format(folder_name))
            folder = self.client.create_folder(folder_name, parent_folder.folder_id)
            parent_folder.add_folder(folder)
        return folder


if __name__ == '__main__':
    mobile_photos_path = input('Mobile photos path: ') or 'Google Photos'
    target_photos_path = input('Path to move photos: ') or ''
    if target_photos_path:
        cataloguer = Cataloguer(mobile_photos_path, target_photos_path)
        cataloguer.catalogue()
    else:
        pass
