from urllib import quote
import requests #pip install requests
import json

from termcolor import colored #pip install termcolor
import time
import sys

import logging
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

class OP5(object):

    def __init__(self, api_url, api_username, api_password, dryrun=False, debug=False, logtofile=False, interactive=False):
        self.api_url = api_url
        self.api_username = api_username
        self.api_password = api_password
        self.dryrun = dryrun
        self.debug = debug
        self.interactive = interactive
        self.data = []
        self.status_code = -1
        self.logtofile = logtofile
        self.modified = False

    def get_debug_text(self,request_type,object_type,name,data):
        #name will always be set except in the "create" case where everything is in "data"
        text = "%s(%s)" % (request_type,object_type)
        if name != "":
            text += " name: %s" % name
        if not data:
            return text

        #data exists
        if object_type in ["host","hostgroup","service"]:
            text += " ("
            interesting_fields = ["service_description","host_name","hostgroup_name","address","hostgroups","contact_groups","check_command","check_command_args"]
            available_fields = filter(lambda x: x in data, interesting_fields)
            text += ', '.join("%s='%s'" % (key,value) for key, value in [(field,data[field]) for field in available_fields])
            text += ")"
            return text
        elif object_type == "change":
            if request_type == "GET":
                return "Got list of changes"
            elif request_type == "POST":
                return "Commit saved"
            elif request_type == "DELETE":
                return "Changes removed"
        else: #for any other object type, print out a generic text
            return "%s(%s) data: %s" % (request_type,object_type,data)

    def create(self,object_type,data_dict):
        return self.operation("POST",object_type,data=data_dict)

    def read(self,object_type,name):
        return self.operation("GET",object_type,name)

    def update(self,object_type,name,data):
        return self.operation("PATCH",object_type,name,data)

    def delete(self,object_type,name):
        return self.operation("DELETE",object_type,name)

    def overwrite(self,object_type,name,data):
        return self.operation("PUT",object_type,name,data)

    def get_changes(self):
        return self.operation("GET","change")

    def undo_changes(self):
        return self.operation("DELETE","change")

    def commit_changes(self, force=False):
        fname = sys._getframe().f_code.co_name
        if not self.modified and not force:
            if self.debug:
                print colored("%s(): Not attempting commit since nothing has been modified" % fname, "yellow")
            return False

        self.get_changes()
        if len(self.data) > 0: #there are changes to commit
            return self.operation("POST","change")
        else:
            print colored("%s(): Not attempting commit since nothing has been modified on the server" % fname, "red")
            return False

    def get_group_members(self,object_type,group_name):
        if object_type in ["hostgroup","contactgroup","servicegroup","usergroup"]:
            if self.read(object_type,group_name):
                if "members" in self.data:
                    return self.data["members"]
            else:
                return []
        else:
            fname = sys._getframe().f_code.co_name
            print colored("%s(): object_type '%s' is not valid" % (fname,object_type), "red")
            return False

    def sync(self,object_type,name,data_at_source):
        if self.read(object_type,name): #get the information currently on the OP5 server
            data_at_destination=self.data
            for key in data_at_source:
                if key not in data_at_destination or set(data_at_source[key]) != set(data_at_destination[key]): #if there is at least one diff, using set() diffs here since order is not important
                    if self.debug:
                        print "Data at source:",data_at_source
                        print "Data at destination:",data_at_destination
                    print key,":",data_at_source[key],"did not match", key,":",data_at_destination.get(key,None),"! Making an update request."
                    return self.update(object_type,name,data_at_source) #send an update request
        else:
            return self.create(object_type,data_at_source)

    def validate(self,request_type,object_type,name,data): 
        if request_type not in ["GET","POST","PATCH","PUT","DELETE"]:
            print colored("%s(%s): Invalid request type! name:'%s' data: %s" % (request_type, object_type, name, str(data) ), "red")
            return False

        if object_type != "change":
            valid_object_types = ["host","hostgroup","service","servicegroup","contact","contactgroup","host_template","service_template","contact_template","hostdependency","servicedependency","hostescalation","serviceescalation","user","usergroup","combined_graph","graph_collection","graph_template","management_pack","timeperiod"]
            if object_type not in valid_object_types:
                print colored("%s(%s): Invalid object type! name:'%s' data: %s" % (request_type, object_type, name, str(data) ), "red")
                return False

            if request_type in ["POST","PATCH","PUT"] and not data:
                print colored("%s(%s): data not set! data: %s" % (request_type, object_type, str(data) ), "red")
                return False
            if request_type in ["PATCH","PUT","DELETE"] and name == "": #GET can have an empty name
                print colored("%s(%s): name not set! data: %s" % (request_type, object_type, str(data) ), "red")
                return False
            if request_type != "POST" and object_type == "service" and name != "" and name.count(";") == 0:
                print colored("%s(%s): Invalid service name! name:'%s' data: %s" % (request_type, object_type, name, str(data) ), "red")
                return False
            if request_type == "POST": #for create, there exists required fields
                # Fact: ALL variables ending in '_name', must be a unique name.
                if object_type == "service":
                    if ("host_name" not in data and "hostgroup_name" not in data) or "service_description" not in data:
                        print colored("%s(%s): Required identifier variables for a service not set in data! data: %s" % (request_type, object_type, str(data) ), "red")
                        return False
                else: #all other object types
                    if object_type+"_name" not in data and "name" not in data:
                        print colored("%s(%s): No identifier variable set in data! data: %s" % (request_type, object_type, str(data) ), "red")
                        return False

        return True

    #CRUD: create, read, update, delete [, and overwrite]
    #INPUTS:
    #object_type: string #e.g. "host","hostgroup","service"
    #name: string
    #data: dictionary
    #RETURNS:
    #boolean indicating success/failure of operation 
    #the response JSON text is loaded into a JSON object and put into self.data
    #the http status code is put into self.status_code
    def operation(self,request_type,object_type,name="",data=None,rdepth=0):
        url = self.api_url + "/config/" + object_type

        if not self.validate(request_type,object_type,name,data):
            return False

        # a little extra code here to fix the service name when referring to a hostgroup in the URL
        if (request_type in ["PATCH","PUT","DELETE"] or (request_type == "GET" and name != "")) and object_type == "service":
            print "INFO: Checking if the given name is a hostgroup first."    
            if self.read("hostgroup",name.split(";")[0]):
                name += "?parent_type=hostgroup"

        if request_type in ["GET","PATCH","PUT","DELETE"] and object_type != "change":
            url += "/" + quote(name.encode("UTF-8"))

        if self.debug:
            text = request_type + " " + url
            if data:
                text += " Sent data: " + str(data)
            print text
        if self.dryrun and request_type != "GET":
            print colored("DRYRUN: "+self.get_debug_text(request_type,object_type,name,data), "yellow")
            return False

        http_headers={'content-type': 'application/json'}

        try:
            r = getattr(requests,request_type.lower()) (url,auth=(self.api_username, self.api_password), verify=False, data=json.dumps(data), headers=http_headers)
        except Exception as e:
            import pprint; pprint.pprint(e)
            return False

        if self.debug:
            print r.status_code
            print r.text
            print r.headers

        try:
            self.data = json.loads(r.text)
        except ValueError as e:
            self.data = r.text
            #GET can return HTTP 200 OK with "index mismatch", but in any other non-success scenario, we should be receiving JSON, and not HTML
            if r.text.find("index mismatch") != -1 or (r.status_code not in [200,201] and r.headers["content-type"].find("text/html") != -1):
                raise e
        self.status_code = r.status_code

        # Do some extra logging in failure cases. #except the 500 Internal Errors
        if r.status_code != 200 and r.status_code != 201 and r.status_code != 500: #200 OK, 201 Created, 500 Internal Error
            #e.g. 400 Bad request (e.g. required fields not set), 409 Conflict (e.g. something prevents it), 401 Unauthorized, 403 Forbidden, 404 Not Found, 405 Method Not Allowed
            print colored("%s(%s): got HTTP Status Code %d %s. Name: '%s'. Sent data: %s" % (request_type, object_type, r.status_code, r.reason, name, str(data)), "red")
            print colored("%s(%s): got HTTP Response: %s" % (request_type, object_type, r.text), "red")
            if self.logtofile:
                logger.error("%s(%s): got HTTP Status Code %d %s. Name: '%s'. Sent data: %s" % (request_type, object_type, r.status_code, r.reason, name, str(data)) )
                logger.error("%s(%s): got HTTP Response: %s" % (request_type, object_type, r.text) )
                logger.debug("%s(%s): HTTP Response headers were: %s" % (request_type, object_type, r.headers) )
            return False
        elif r.status_code == 500: #500 Internal Error
            rdepth+=1
            if rdepth < 3:
                json_obj = json.loads(r.text)
                if json_obj['error'] == "Export failed" and json_obj['full_error']['type'] == "nothing to do":
                    return False
                time.sleep(6)
                return self.operation(request_type,object_type,name,data,rdepth)
            else:
                raise RuntimeError("Bailing out after 3 retries on HTTP 500 Internal Error")

        #success! #200 OK, 201 Created

        #debug/status text
        if not self.interactive: #in interactive mode, skip the status text for successful requests, so that the JSON output can easily be piped into another command
            print colored(self.get_debug_text(request_type,object_type,name,data), "green")
        #log (successful) changes
        if request_type != "GET" and self.logtofile:
            logger.info(self.get_debug_text(request_type,object_type,name,data))

        if request_type != "GET" and object_type != "change": #if it is not a "read" request or a "commit" request
            self.modified = True
        elif object_type == "change" and (request_type in ["POST","DELETE"] or (request_type == "GET" and len(self.data) == 0)):
            self.modified = False #reset the modified flag after a successful commit, or after understanding that there is nothing to commit
        return True

