# Secondary Search
When using the search functionality on the Job Log, we often run into an issue where the currently selected filter, say Fab, filters out the job-release we are searching for, so we get a silent failure. User thinks we are missing a job-release, but actually it is simply filter gated. 

# Fix
In the table element, below the job-release not found element, we want to display the output of their search.
- Warning message says something like '{search keyword(s)} not found under Fab'
- Secondary search shows result of actual search if search keywords found elsewhere

# Quality of Life
User will often look up a job-release as '350-567'. We want them to be able to use the dash to search for that explicit job release. currently we are dropping that -, which is not best practice for the user
