import requests
import os
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from typing import List, Tuple, Optional, Dict, Any

# Load environment variables from .env file
load_dotenv()

# Configuration
SONAR_TOKEN = os.getenv('SONAR_TOKEN', '')
DEFAULT_SNOOZE_DAYS = int(os.getenv('DEFAULT_SNOOZE_DAYS', 30))
SONARQUBE_URL = os.getenv('SONARQUBE_URL', 'http://localhost:9000')

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create a session object
session = requests.Session()
session.headers.update({'Authorization': f'Bearer {SONAR_TOKEN}'})

def get_issues() -> List[Dict[str, Any]]:
    url = f'{SONARQUBE_URL}/api/issues/search'
    params = {
        'issueStatuses': 'ACCEPTED',
        'ps': 500  # Page size, adjust as needed
    }
    issues = []
    page = 1
    while True:
        params['p'] = page
        logger.info(f'Fetching issues, page {page}')
        response = session.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        issues.extend(data['issues'])
        if page >= data['paging']['total']:
            break
        page += 1
    return issues

def get_issue_changelog(issue_key: str) -> Dict[str, Any]:
    url = f'{SONARQUBE_URL}/api/issues/changelog'
    params = {'issue': issue_key}
    response = session.get(url, params=params)
    response.raise_for_status()
    return response.json()

def find_resolution_date(changelog: Dict[str, Any]) -> Optional[datetime]:
    for entry in changelog['changelog']:
        for diff in entry['diffs']:
            if diff['key'] == 'issueStatus' and diff['newValue'] == 'ACCEPTED':
                return datetime.strptime(entry['creationDate'], '%Y-%m-%dT%H:%M:%S%z')
    return None

def reopen_issue(issue_key: str) -> Dict[str, Any]:
    url = f'{SONARQUBE_URL}/api/issues/do_transition'
    data = {'issue': issue_key, 'transition': 'reopen'}
    response = session.post(url, data=data)
    response.raise_for_status()
    return response.json()

def remove_snooze_tag(issue_key: str, tag: str) -> Dict[str, Any]:
    url = f'{SONARQUBE_URL}/api/issues/tags/remove'
    params = {'issue': issue_key, 'tags': tag}
    response = session.post(url, params=params)
    response.raise_for_status()
    return response.json()

def parse_snooze_tag(tags: List[str]) -> Tuple[int, Optional[str]]:
    for tag in tags:
        if 'snooze' in tag:
            try:
                return int(tag.split('_')[1]), tag
            except (IndexError, ValueError):
                continue
    return DEFAULT_SNOOZE_DAYS, None

def process_issue(issue: Dict[str, Any]) -> None:
    issue_key = issue['key']
    changelog = get_issue_changelog(issue_key)
    resolution_date = find_resolution_date(changelog)
    if resolution_date is None:
        logger.warning(f'No resolution date found for issue {issue_key}')
        return

    snooze_days, snooze_tag = parse_snooze_tag(issue['tags'])
    snooze_deadline = resolution_date + timedelta(days=snooze_days)
    
    if datetime.now(tz=resolution_date.tzinfo) > snooze_deadline:
        logger.info(f'Reopening issue {issue_key} (snooze expired)')
        reopen_issue(issue_key)
        logger.info(f'Issue {issue_key} reopened')
        if snooze_tag:
            remove_snooze_tag(issue_key, snooze_tag)
            logger.info(f'Tag {snooze_tag} removed from issue {issue_key}')

def main() -> None:
    issues = get_issues()
    for issue in issues:
        if any('snooze' in tag for tag in issue['tags']):
            process_issue(issue)

if __name__ == '__main__':
    main()