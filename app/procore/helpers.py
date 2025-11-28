import pandas as pd
# Helper function to convert pandas NaT/NaN to None
def clean_value(value):
    if pd.isna(value):
        return None
    # If it's a pandas Timestamp, convert to Python datetime
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime() if not pd.isna(value) else None
    return value

def parse_ball_in_court_from_submittal(submittal_data):
    """
    Parse the users assigned to ball_in_court and approvers from submittal webhook data.
    Handles multiple assignees by returning a comma-separated string.
    
    Args:
        submittal_data: Dict containing submittal data from Procore webhook
        
    Returns:
        dict: {
            'ball_in_court': str or None - Comma-separated list of user names/logins who have the ball in court,
                                          or single user name/login if only one person,
            'approvers': list - List of approver data from the submittal
        }
        Returns None if submittal_data is not a valid dict
    """
    if not isinstance(submittal_data, dict):
        return None
    
    # Get approvers list
    approvers = submittal_data.get("approvers", [])
    if not isinstance(approvers, list):
        approvers = []
    
    ball_in_court_users = []
    
    # First, check if ball_in_court array has entries
    ball_in_court = submittal_data.get("ball_in_court", [])
    if ball_in_court and isinstance(ball_in_court, list) and len(ball_in_court) > 0:
        # Extract user info from ALL ball_in_court entries (not just the first)
        for entry in ball_in_court:
            if isinstance(entry, dict):
                user = entry.get("user") or entry
                if user and isinstance(user, dict):
                    name = user.get("name")
                    if name:
                        ball_in_court_users.append(name)
                    else:
                        login = user.get("login")
                        if login:
                            ball_in_court_users.append(login)
    
    # If ball_in_court is empty, derive from approvers with pending responses
    if not ball_in_court_users and approvers:
        # Find ALL approvers who need to respond (pending state)
        for approver in approvers:
            if not isinstance(approver, dict):
                continue
                
            response_required = approver.get("response_required", False)
            if not response_required:
                continue
            
            response = approver.get("response", {})
            if not isinstance(response, dict):
                continue
            
            # Check if response is pending
            response_considered = response.get("considered", "").lower()
            response_name = response.get("name", "").lower()
            
            # Consider it pending if:
            # - considered is 'pending'
            # - name is 'pending'
            # - or distributed is False (not yet sent)
            is_pending = (
                response_considered == "pending" or
                response_name == "pending" or
                not approver.get("distributed", False)
            )
            
            if is_pending:
                user = approver.get("user")
                if user and isinstance(user, dict):
                    name = user.get("name")
                    if name and name not in ball_in_court_users:
                        ball_in_court_users.append(name)
                    else:
                        login = user.get("login")
                        if login and login not in ball_in_court_users:
                            ball_in_court_users.append(login)
    
    # Return comma-separated string if multiple users, single string if one, None if empty
    if not ball_in_court_users:
        ball_in_court_value = None
    elif len(ball_in_court_users) == 1:
        ball_in_court_value = ball_in_court_users[0]
    else:
        # Multiple users - join with comma and space
        ball_in_court_value = ", ".join(ball_in_court_users)
    
    return {
        "ball_in_court": ball_in_court_value,
        "approvers": approvers
    }