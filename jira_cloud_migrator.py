import requests, os, json, csv, logging
from datetime import datetime
from requests.auth import HTTPBasicAuth 
from pathlib import Path
from dotenv import load_dotenv

# Get the current date and time
now = datetime.now()

script_directory = os.path.dirname(os.path.abspath(__file__))

# Define the log file path relative to the script's directory
log_file_path = os.path.join(script_directory, f"script_log_{now.strftime('%Y-%m-%d')}.log")
logging.basicConfig(filename=log_file_path, level=logging.INFO, format='%(asctime)s %(message)s')

### Path to .evn file with API tokens needs to be specified
env_path = Path('Tokens/.env')
load_dotenv(dotenv_path=env_path)
###Jira token needs to be named <TOKEN> in the .env file
jira_token=os.environ['TOKEN']

### Defined Jira Cloud tenant URLs
tenant_1 = "https://example1.atlassian.net/"
tenant_2 = "https://example2.atlassian.net/"
tenant_3 = "https://example3.atlassian.net/"
tenant_4 = "https://example4.atlassian.net/"


### Jira Administators email address who generated the token needs to be specified "email@example.com"
auth = HTTPBasicAuth("email@example.com", jira_token)

### Headers used for Jira API calls
headers = {
  "Accept": "application/json",
  "Content-Type": "application/json"
}

### Function to create an array containing source Jira email and target Jira account email based on the input CSV file

users = []

def csvToArray():
  file_csv = input("Enter CSV file's name of a CSV file containing source and destination email addresses of Jira accounts: ")
  while True:
    try:
      with open(file_csv, newline = '') as csvfile:
        reader = csv.reader(csvfile) 
        for row in reader: # each row is a list
          users.append(row)
        break  
    except FileNotFoundError:
      file_csv = input("Entered File name is either incorrect of such file does not exist/is located in a wrong directory.\nPlease try again: ")

### Function gets Jira accountId based on the email address
def getAccountId(email, tenant):
    response = requests.get(f'{tenant}/rest/api/3/user/search?query={email}', headers=headers, auth=auth)
    if response.status_code == 200:
      userOutput = json.loads(response.text)
      if userOutput != []:
        accountId = userOutput[0]['accountId']
        logging.info("Account ID:{} for email: {} fetched successfully!".format(accountId, email))
        return accountId
      else:
        logging.error('200 response from the server, but accountId for user {} was not fetched. Try to find this user in another tenant.'.format(email)) 
    elif response.status_code != 200:
      logging.error("FAILED to fetch Account ID for email: {} with ERROR code: {}".format(email, response.status_code))

### Functions fecthes all issues assigned to a Jira user
def getAssignedIssues(user, tenant):
    email = user[0]
    response = requests.get(f'{tenant}/rest/api/3/search?jql=assignee%20in%20("{email}")&maxResults=100', headers=headers, auth=auth)
    if response.status_code == 200:
        userOutput = json.loads(response.text)
        total_issues = userOutput['total']
        while total_issues > 1:
          response = requests.get(f'{tenant}/rest/api/3/search?jql=assignee%20in%20("{email}")&maxResults=100', headers=headers, auth=auth)
          logging.info("Jira issues for user {} were fetched successfully!".format(email))
          userOutput = json.loads(response.text)
          for issue in userOutput['issues']:
            issueId = issue['id']
            reassignIssues(issueId, user, tenant)
          total_issues = total_issues - 100
    elif response.status_code != 200:
        logging.error("Failed to fetch Jira issues for user {} with ERROR code: {}".format(email, response.status_code))

### Function reassigns issues fetched by getAssignedIssues function to a destination account provided in the CSV file
def reassignIssues(issueId, user, tenant):
    body = {
      "accountId": getAccountId(user[1], tenant)
    }
    response = requests.put(f'{tenant}/rest/api/3/issue/{issueId}/assignee', headers=headers, auth=auth, json = body)
    if response.status_code == 204:
      logging.info("Jira issue {} was reassigned successfully!".format(issueId))
    elif response.status_code != 204:
      logging.error("Failed to reassign issue with ID: {} with ERROR code: {}".format(issueId, response.status_code))

### Function to fetch all issues were provided user is a reporter
def getReportedIssues(user, tenant):
    email = user[0]
    response = requests.get(f'{tenant}/rest/api/3/search?jql=reporter%20in%20("{email}")&maxResults=100', headers=headers, auth=auth)
    if response.status_code == 200:
        userOutput = json.loads(response.text)
        total_issues = userOutput['total']
        logging.info("Jira issues for user {} were fetched successfully!".format(email))
        while total_issues > 1:
          response = requests.get(f'{tenant}/rest/api/3/search?jql=reporter%20in%20("{email}")&maxResults=100', headers=headers, auth=auth)
          userOutput = json.loads(response.text)
          for issue in userOutput['issues']:
            issueId = issue['id']
            updateReporter(issueId, user, tenant)
          total_issues = total_issues - 100
    elif response.status_code != 200:
        logging.error("Failed to fetch Jira issues for user {} with ERROR code: {}".format(email, response.status_code))

### Function which updates all issues fetched by getReportedIssues and updates reported to the destination email provided in the CSV file
def updateReporter(issueId, user, tenant):
  body = {
     "fields": {
        "reporter": {
        "accountId": getAccountId(user[1],tenant)
    }
  }}
  response = requests.put(f'{tenant}/rest/api/3/issue/{issueId}', headers=headers, auth=auth, json = body)
  if response.status_code == 204:
    logging.info("Jira issue reporter {} was updated successfully!".format(issueId))
  elif response.status_code != 204:
    logging.error("Failed to update reporter of issue with ID: {} with ERROR code: {}".format(issueId, response.status_code))

### Function fetches groups user is in and adds them to a dictionary containing group's ID and name
def getGroups(user, tenant):
    groups_dict = {}
    accountId = getAccountId(user[0], tenant)
    response = requests.get(f'{tenant}/rest/api/2/user/groups?accountId={accountId}', headers=headers, auth=auth)
    groupOutput = json.loads(response.text)
    if response.status_code == 200:
        logging.info("Groups for user: {} were fetched successfully!".format(user[0]))
        for group in groupOutput:
            groups_dict.update({group['groupId']:group['name']})
    elif response.status_code != 200:
            logging.info("FAILED to fetch groups for user: {}.".format(user[0]))   
    return groups_dict  

### Function adds user to the groups based on the provided accountId and list with group IDs
def addToGroups(user, tenant):
    user_email= user[1]
    body = {
      "accountId": getAccountId(user[1], tenant)
    }
    groups_dict = getGroups(user, tenant)
    for groupId in groups_dict.keys():
        response = requests.post(f'{tenant}/rest/api/2/group/user?groupId={groupId}', headers=headers, auth=auth, json = body)
        if response.status_code == 201:
          logging.info("{} was added to the group {} successfully!".format(user_email, groups_dict[groupId]))
        else:
          logging.error("FAILED to add {} to the group: {} with ERROR code: {}".format(user_email, groups_dict[groupId], response.status_code))


### Main function containing selection cases
def main():
      logging.info('Script Started!')
      csvToArray()
      choose_tenant = input("Select the Jira Cloud tenant in which you would like to update users."
        "\nTo select Tenant 1: 1"
        "\nTo select Tenant 2: 2"
        "\nTo select Tenant 3: 3"
        "\nTo select Tenant 4: 4"
        "\nYour input: ")
      
      while choose_tenant not in ['1', '2', '3', '4']:
        print('Wrong input! Only enter only numbers" [1, 2, 3, 4] are accepted.')
        choose_tenant = input("Select the Jira Cloud tenant in which you would like to update users."
        "\nTo select Tenant 1: 1"
        "\nTo select Tenant 2: 2"
        "\nTo select Tenant 3: 3"
        "\nTo select Tenant 4: 4"
        "\nYour input: ")
        
      if choose_tenant == '1':
        tenant = tenant_1
      elif choose_tenant == '2':
        tenant = tenant_2
      elif choose_tenant == '3':
        tenant = tenant_3
      elif choose_tenant == '4':
        tenant = tenant_4
      else:
        logging.error('Unexpected ERROR, no input in range 1, 2, 3, 4!')
      input_case = input("----------------------------------------------------------------\nTo transfer all Jira issues and group memberships enter: 1" 
        "\nTo transfer all Jira issues enter: 2"
        "\nTo transfer all Jira group memberships enter: 3"
        "\nYour input: ")
      while input_case not in ['1', '2', '3']:
        print('Wrong input! Only enter only numbers" [1, 2, 3] are accepted.')
        input_case = input("To transfer all Jira issues and group memberships enter: 1"
        "\nTo transfer all Jira issues enter: 2 \nTo transfer all Jira group memberships enter: 3 \nYour input: ")
      print("Running...")
      for user in users:
          if input_case == '1':
              getGroups(user, tenant)
              addToGroups(user, tenant)
              getAssignedIssues(user, tenant)
              getReportedIssues(user, tenant)
          elif input_case == '2':
              getAssignedIssues(user, tenant)
              getReportedIssues(user, tenant)
          elif input_case == '3':
              getGroups(user, tenant)
              addToGroups(user, tenant)
          else:
              logging.error('Unexpected ERROR, no input in range 1, 2, 3!')
      logging.info('Run Completed!')
      print("Run Completed!")

### Run Main    
main()