# Fab Order Testing
We are testing fab order functionality. In the short term, we want to refrain from passing Brain Fab Order updates for releases to Trello API. 

# Desired Behavior
- Track Event and Update DB
- Do NOT send Trello API call to update Fab Order custom field
- Onedrive updates will still update Fab Order

# Important
- This is a Brain -> Trello disablement only! 

# Relevant Files
app/brain/job_log/engine/routes/services
