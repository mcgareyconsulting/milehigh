# Drafting Work Load Submittal Ordering
Context document describing ordering behavior and user controls.

# Ordering Behavior
- Submittals are ordered per user ball_in_court.
- Submittals with multiple users in ball_in_court cannot be reordered.
- Three ordering buckets (Unordered, Ordered, and Urgent)

## Unordered
- All submittals without an order number, implicitly filtered in ascending last_bic_update

## Ordered
- All submittals for ball_in_court user 1-x.
- No automatic compression of this list.
- List only compressed when resort button pushed on that bic user's filter.
- Submittal bumped into order with the 'bump' button gets order # x+1.

## Urgent
- Each ball_in_court user gets 9 urgency slots (0.1-0.9) most urgent to least urgent.
- An ordered submittal that receives a bump gets assigned 0.9, pushing any other urgent submittals up.
- All urgent submittals compress automatically down to 0.9 as submittals are added and removed.

## User Actions
### Bump button
- Bumps submittal into next ordering group (Unordered -> Ordered, Ordered -> Urgent)
- Always an upward group jump

### Arrow Scalar
- Single step order adjustment.
- Ordered list, up arrow on 7 would swap submittals 7 with 6. Vice versa
- Urgent list, down arrow on 0.8 would swap with submittal 0.9. Vice versa.
- No jumps between groups. Single step inside particular group only.

### Drag N Drop
- Allows movements between order type groups.
- Dropping an ordered or urgent submittal into the unordered group will drop its order number.
- Dropping submittal 11 between submittals 2 and 3. Assign 11->3 and cascade down.
- Dropping any ordered or unordered submittal in urgency bucket, or dop target above submittal 1 will always assign 0.9 and push other urgents up, while maintaining donward compression.
- Picking up and dropping submittal in same spot has no api or animation.

# Important
- No page reload on submittal movements.
- Submittals with status closed drop order number to make room for now ones.
- Must lock to ball_in_court group.
