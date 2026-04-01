# Start Install Cascade
Releases on the job log without a specifically set red date should have a start install date that cascades and adjusts as releases change staging. This is an application of the fabrication hours function. The current stage of a release has an impact on the fabrication hours it has left, compared against the fab hours placed in the bid. Releases that change stages have less fabrication, which means we adjust the start installation dates for releases behind it in the pipeline. This is an estimation tool.

# Goal
- Confirm that releases with 'red date'/confirmed start install date are not affecting start install cascade. 
- Want to confirm the application of the start install cascade formulas for releases.
- Total fabrication hours and total install hours calculations are correct, so we can confidently build upon those pieces of the start install cascade formula.
- Please verify with me the setup of the start install cascade
- This cascade should run dynamically, without input from the user. Currently, the user must push reschedule.
- If you are comparing against current db values, it appears that the formula is working correctly and dates are close, but red dates might be impacting.

# Potential Trip UP
- It could be the case that start install is workign perfectly, but the previously broken fabrication order on releases and out of date data have made it appear that the start install cascade is working incorrectly. We probalby need to make it dynamic, but highly likely that the formula is fine and my client needs to do a better job of keeping fab orders up to date.
