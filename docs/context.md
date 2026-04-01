# Stage/Status Scroll Wheel Behavior
User wants improved dropdown / scroll wheel behavior on the stage column of the job log.

# Improved Behavior
- User wants the Stage dropdown to roll over and behave like a wheel. 
- When opened, the current stage should be at the top, with the next logical stage next, obviously.
- The dropdown will roll over like a wheel, maintaining focus on current stage and next logical stage.

# Bugs
- When interacting with the dropdown at the bottom of the releases table, the dropdown will extend below the table element and be inaccessible.
- In this case, the dropdown should expand upward instead of downward. We never want the dropdown element to render outside of the releases table
- There are occasionally scrolling lockouts with an open dropdown. I have occasionally opened a dropdown, scrolled the table to far, so the dropdown is not visible and this locks the scroll on the actual page. Need to tighten up the dropdown behavior overall

# Ask Clarifying Questions
