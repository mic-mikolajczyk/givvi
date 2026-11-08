# App idea

## Core concept

Idea of this app is to manage family and friend events based on the "secret santa" concept.
This app should organize participants into events, assign Secret Santa, and manage gift exchanges efficiently. Additionally it should track individual wishlist items.

## Base model

- User: Represents an individual using the app, who can create events, invite participants.
- Event admin user: Represents the user who created and manages the event.
- Event: Represents a family or friend gathering for which Secret Santa is organized.
- Participant: Represents a person invited to the event. Participant name can be different from their user name but each participant must be associated with a user.
- Gift: Represents a gift idea or wish list item associated with a participant.
- Wishlist: Represents a collection of gift ideas or wish list items associated with a user. Each user can have only one wishlist.
- Assignment: Represents the pairing of a Secret Santa with their assigned recipient.

## Standard flow

0. User registration and login
1. User creates an event and becomes the event admin.
2. Event admin creates a participants list for the event. This is not an invitation list; it simply defines who will be part of the Secret Santa exchange.
3. Admin can send the invitation to other users by email or through the app.
4. Users are entering the event and accepting their participation. They need to confirm who they are from the participants list.
5. If Admin user enables drawing, participants can view their assigned recipients.
6. Participants can see on the event page the list of participants, event details, link to each participant wishlist and gift exchange status.

- Users create and manage their wishlists on their dashboard
- Users create and manage their events on their dashboard
- Participants view their assigned recipients and gift ideas.
- Event admin triggers reminders and notifications as needed.

## Event Participants

### Event admin

- The user who created the event
- Can set event details:
  - location
  - description
  - maximum price of gifts (with currency).
- Manage the list of participants, including adding or removing or renaming participants before the Secret Santa assignment.
- Turn on and off the Secret Santa assignment feature. Until it is turned on, participants cannot view (draw) their assigned recipients.

### Regular Participant

A user invited to the event, after assignment, Can view the list of other participants and link to their wishlists. After drawing the name, drawing is unavailable and the assigned recipient is fixed.

## Features

### Create and manage events

- Creation of new events is possible via events dashboard
- Editing and managing existing events is also done through the events dashboard
- Deleting events is also managed through the events dashboard
- Only Admin of the event can delete the event.
- Event can be archived by the admin, making it read-only for all participants.
- Archived events can be unarchived by the admin if needed.
- During creation of the event, the admin can set the initial event details, including location, description, and maximum price of gifts. This can be edited afterwards. Name of the event is obligatory.
- During creation, list of participants need to be set by the admin.
- Participants name are not related to user accounts; they are simply identifiers within the event.
- Everybody (even admin) during first entering the event needs to confirm their identity from the participants list.

### Invite family and friends

- After event creation, admin can sent and invitation to user of the app
- Invitation should be also possible via link. Link should provide registration or login first
- everybody can send invitation but only admin can create and adit list of participants.

### Assign secret santa participants - aka Drawing Names

- Drawing process at the event can be disabled or enabled
- Drawing names in disabled by default after event creation - Draw name button for participant is disabled
- Event Admin can enable drawing
- After enabling the drawing - assignment of the "secret Santa" is done secretly
- All participants should have enabled button to draw a name only when drawing is enabled. If disabled - button should be show as disabled as well
- After drawing a name, button should disappear and should be replaced by the drawn name
- Drawing should be animated or take some time to simulate drawing process (assignment is done during enabling the drawing but user should have a feeling that drawing is processed during button press)
- Admin can disable drawing when it was enabled. Then all assignments are reset. This is due to possibility to add new participants (when new participant joins and drawing is already done, it is not possible to not draw myself)
- Editing list of participants by the admin should be only possible when drawing is disabled

### Track gift ideas and wish lists

- Each user can create its own wishlist of gifts
- Each gift can be defined by the name (obligatory), description, price, link (to online shop or picture)
- when price is not set it should be explicitly shown as not known
- Gifts order can be customized to visualize priority
- Other users can view other users wishlists
- When some user would like to see other users wishlist directing from the event, gifts which are more expensive then event budget should be visually marked somehow.

### Wishlist

- Allows users to manage their own wishlist, including adding, editing, and removing gifts.
- Allows users to set the priority of gifts by arranging them in order.
- There is one wishlist per user. This wishlist can be viewed by other participants through the event dashboard.
- When whishlist is viewed by others, it is customized by the event budget, highlighting gifts that exceed the set budget.
- When the wishlist is viewed by others, others can mark gifts as purchased or reserved, which will be visible to all participants except the owner of the wishlist.

### Secret Santa Assignment

- Allows event admin to enable or disable the drawing process.
- Participants can draw a name only when the drawing is enabled.
- After drawing a name, participants see the assigned recipient.
- Admin can reset the drawing, which clears all assignments. this is done by disabling the drawing and then re-enabling it.

## App Views

App should have a user-friendly interface that allows easy navigation between different sections.
After standard Login or Registration, users are directed to the Main Dashboard.
Main home view consists of 3 tabs/dashboards: "Events", "Wishlist", and "Profile". Access is through the main navigation menu on the bottom of the screen.

Each view should be a dedicated page. No pop-ups or modal windows should be used for primary navigation between views.

### Main Dashboard

- Displays events and enables to enter the event
- Events are grouped by their status (upcoming, ongoing, past).
- Possibility to create an event

### Wishlist

- View to manage wishlist
- User can create, read, update, and delete gifts in their wishlist.
- Allows to set priority by setting the order from top to bottom
- Other participants can view the user's wishlist.
- Allows to mark gifts as purchased or reserved by other participants - This cannot be seen by the user itself. it is only visible to other participants.

### Event Details - Event dashboard

- Shows event information
- List of participants, 
- gift exchange status: If drawing is enabled and if the participant already has an assigned recipient, it should be indicated.
- Admin has access to editing and drawing enabling controls

### Wishlist of Other Participants

- View to see the wishlists of other participants in the event.
- Accessed from the event dashboard by clicking specific participant's name or avatar.
- Allows users to see which gifts have been purchased or reserved by others.
- Does not allow editing of other participants' wishlists.
- gifts which have defined price above budget are highlighted, marked or greyed out to indicate they exceed the set budget.
- After reviewing the wishlist of other participants, users can return to the event dashboard to view other participants' wishlists.

### Profile

- Displays user profile information
- Allows users to edit their personal details and preferences
- In this section, users can view and manage their profile settings like: language, theme, Name and surename, email, and password.
- Users can also log out from this section.

## Technical Details

- The app should be built with a focus on user experience, ensuring smooth navigation between events, participants, and wishlists.
- The app should handle real-time updates to reflect changes in participant lists, gift ideas, and Secret Santa assignments promptly.
- Security and privacy should be considered, especially in handling user data and Secret Santa assignments.
- The app should be designed to be scalable, accommodating a growing number of users and events without compromising performance.
- The app should be maintainable, with a clear code structure and documentation to facilitate future development and updates.

## Tech Stack

- Frontend: Vue.js
- CSS: Tailwind CSS
- Backend: Python, Flask
- Database: PostgreSQL, SQLite for testing
- Deployment: Docker, Kubernetes
