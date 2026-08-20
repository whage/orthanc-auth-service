# SPDX-FileCopyrightText: 2022 - 2026 Orthanc Team SRL <info@orthanc.team>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import orthanc
import pprint
import json
import re
import time
import threading
import typing
import datetime
import base64

# This plugin adds API routes to perform custom actions after an upload in the inbox.
# This inbox does not have a form but simply add a label with the username.

def from_dicom_date(dicom_date: str) -> datetime.date:
    if dicom_date is None or len(dicom_date) == 0:
        return None
    m = re.match('(?P<year>[0-9]{4})(?P<month>[0-9]{2})(?P<day>[0-9]{2})', dicom_date)
    if m is None:
        raise ValueError("Not a valid DICOM date: '{0}'".format(dicom_date))
    return datetime.date(int(m.group('year')), int(m.group('month')), int(m.group('day')))

def to_dicom_date(date: datetime.date) -> str:
    if date:
        return '{0:4}{1:02}{2:02}'.format(date.year, date.month, date.day)
    return None

def get_first_day_of_year(date):
    if date:
        return datetime.date(date.year, 1, 1)
    return None

def get_user_id(request):
    # decode the JWT keycloak token.  We don't verify the signature here because, it we get here,
    # it means that it has passed the token verification in the auth-plugin and we can trust the token.
    if 'headers' in request and 'token' in request['headers']:
        
        _, payload, __ = request['headers']['token'].split('.')
        payload += '=' * (-len(payload) % 4) 
        
        decoded_keycloak_token = json.loads(base64.b64decode(payload).decode('utf-8'))
        if 'sub' in decoded_keycloak_token: # this is a keycloak token
            return decoded_keycloak_token['sub']
        elif 'username' in decoded_keycloak_token: # this is an inbox-token
            return decoded_keycloak_token['username']

    return None

def sanitize_user_id_for_label(user_id: str) -> str:
    return re.sub(r'[^0-9\-_a-zA-Z]', '_', user_id)


store_lock = threading.Lock()
current_commit_id = 0

# Orthanc Rest API callback called after every upload in the inbox
def on_post_inbox_commit(output, uri, **request):
    global current_commit_id
    global store_lock

    user_id = get_user_id(request)

    if request['method'] != 'POST':
        output.SendMethodNotAllowed('POST')

    payload = json.loads(request['body'])
    uploaded_studies_ids = payload["OrthancStudiesIds"]

    if len(uploaded_studies_ids) > 1:
        message = f"Wait while {len(uploaded_studies_ids)} studies are being labeled"
    else:
        message = f"Wait while the study is being labeled"

    with store_lock:
        current_commit_id += 1

    sanitized_label = sanitize_user_id_for_label(user_id=user_id)

    for uploaded_study_id in uploaded_studies_ids:
        orthanc.RestApiPut(f"/studies/{uploaded_study_id}/labels/{sanitized_label}", "")
        
        response = {
            "CommitId": current_commit_id,
            "Message": message
        } 

    output.AnswerBuffer(json.dumps(response), 'application/json')


# Orthanc Rest API callback called to monitor processing after a commit.
# In this sample, the jobs are completed immediately
def on_post_monitor_processing(output, uri, **request):
    global store_lock
    global commit_jobs

    if request['method'] != 'POST':
        output.SendMethodNotAllowed('POST')

    # the payload is the response from the commit route
    payload = json.loads(request['body'])

    commit_id = payload["CommitId"]
    response = {}

    response = {
        "PctProcessed": 100,
        "HasFailed": False,
        "IsComplete": True,
        "Message": "Study uploaded and labeled"
    }

    output.AnswerBuffer(json.dumps(response), 'application/json')





orthanc.RegisterRestCallback('/plugins/inbox/commit', on_post_inbox_commit)
orthanc.RegisterRestCallback('/plugins/inbox/monitor-processing', on_post_monitor_processing)
