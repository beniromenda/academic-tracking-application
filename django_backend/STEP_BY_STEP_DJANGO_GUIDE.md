# Step-by-Step Django Guide (Beginner Friendly)

This guide follows the exact order you should use as a beginner.

## 1) Open the Django project folder

From your workspace root:

```powershell
cd django_backend
```

## 2) Confirm Django version

```powershell
py -m django --version
```

Use Django 5.1+ for Python 3.13 compatibility.

## 3) Install dependencies for this Django app

```powershell
py -m pip install -r requirements.txt
```

## 4) Run database migrations

```powershell
py manage.py makemigrations
py manage.py migrate
```

## 5) Create your first admin user

```powershell
py manage.py createsuperuser
```

Enter username, email, and password when prompted.

## 6) Start the Django development server

```powershell
py manage.py runserver
```

Open this URL in your browser:

http://127.0.0.1:8000/

## 7) Login

Use the superuser account created above.

## 8) Create user accounts in order

Open Users page and create:

- Administrator account(s)
- Teacher account(s)
- Learner account(s)

Important: choose the correct Role for each account.

## 9) Create learner profiles

Open Learners page and create learner profiles.

Each learner profile links to one learner user account.

## 10) Create competencies

Open Competencies page and create competency records.

Example:

- Code: COMP-001
- Name: Numeracy

## 11) Create assessment tasks

Open Tasks page and create tasks linked to competencies.

Example:

- Task title: Midterm Numeracy Task
- Competency: COMP-001

## 12) Record assessment results

Open Results page and record learner results for tasks.

Validation included:

- score must be between 0 and 100
- each learner-task pair is unique (no duplicate result rows)

## 13) Generate reports and dashboard insights

- Dashboard page: cards + competency chart + class summary
- Reports page: filter by class, competency, and rating
- Feedback page: learner-facing feedback view

## 14) Optional: Use Django admin panel

Open:

http://127.0.0.1:8000/admin/

You can manage all records from admin as well.

## 15) Common beginner troubleshooting

If server does not start:

- ensure you are in django_backend folder
- rerun migrations
- verify Django version with py -m django --version

If login fails:

- verify user exists in Users table/admin
- verify account status is Active

If you get permission denied pages:

- admin-only pages require Administrator role or superuser
- teacher pages require Teacher or Administrator

## Implemented Features Mapped to Your PDF

- User authentication and role-based access
- User account management (CRUD)
- Learner management (CRUD + search)
- Competency management (CRUD)
- Assessment task management (CRUD)
- Assessment result management (CRUD)
- Report generation with filtering
- Interactive dashboard with chart
- Data validation and duplicate prevention
