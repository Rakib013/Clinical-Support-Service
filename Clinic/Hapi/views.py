import requests
from django.shortcuts import render, redirect
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login, authenticate, logout
from .forms import UserRegistrationForm, DoctorRegistrationForm, PatientRegistrationForm, LoginForm
from .fhir_utils import create_practitioner_in_fhir, create_patient_in_fhir, get_fhir_data  # Import the functions
from django.contrib.auth.decorators import login_required
from django.contrib import messages

FHIR_SERVER_URL = 'http://localhost:8080/fhir/'

# Create the view for the landing page
def landing_page(request):
    return render(request, 'landing_page.html')

# View for registering a new user (Doctor or Patient)
def register(request, role):
    if request.method == 'POST':
        user_form = UserRegistrationForm(request.POST)
        print(user_form.is_valid(), "User")
        if user_form.is_valid():
            user = user_form.save(commit=False)
            user.role = role  # Assign role before saving
            user.username = user.email
            #user.save()  # Save CustomUser instance first

            # Handle Doctor registration
            if role == 'doctor':
                doctor_form = DoctorRegistrationForm(request.POST)
                print(doctor_form.is_valid(), "doctror")
                if doctor_form.is_valid():
                    doctor = doctor_form.cleaned_data  # Extract cleaned data
                    fhir_id = create_practitioner_in_fhir(doctor)  # Pass dict, handle in function
                    print(fhir_id)
                    if fhir_id:
                        user.fhir_id = fhir_id  # Save the FHIR ID to CustomUser
                        user.save()
                    login(request, user)
                    messages.success(request, f"Welcome, {user.email}!")
                    return redirect('Hapi:dashboard')  # Redirect to user_dashboard or home page

            # Handle Patient registration
            elif role == 'patient':
                patient_form = PatientRegistrationForm(request.POST)
                print(patient_form.is_valid(), "patient")
                if patient_form.is_valid():
                    patient = patient_form.cleaned_data  # Extract cleaned data
                    fhir_id = create_patient_in_fhir(patient)  # Pass dict, handle in function
                    print(fhir_id)
                    if fhir_id:
                        user.fhir_id = fhir_id  # Save the FHIR ID to CustomUser
                        user.save()
                    login(request, user)
                    messages.success(request, f"Welcome, {user.email}!")
                    return redirect('Hapi:dashboard')  # Redirect to user_dashboard or home page

        # If form is invalid, re-render with errors
        return render(request, 'register.html', {
            'role': role,
            'user_form': user_form,
            'doctor_form': DoctorRegistrationForm() if role == 'doctor' else None,
            'patient_form': PatientRegistrationForm() if role == 'patient' else None
        })
    
    else:
        user_form = UserRegistrationForm()
        doctor_form = DoctorRegistrationForm() if role == 'doctor' else None
        patient_form = PatientRegistrationForm() if role == 'patient' else None
        
        return render(request, 'register.html', {
            'role': role,
            'user_form': user_form,
            'doctor_form': doctor_form,
            'patient_form': patient_form
        })

def user_login(request):
    if request.user.is_authenticated:
        print("Yeap")
        return redirect('Hapi:dashboard')
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password"]
            
            user = authenticate(request, username=email, password=password)  # Use email as username
            
            if user is not None:
                login(request, user)
                print("Logg")
                messages.success(request, f"Welcome, {user.email}!")
                return redirect('Hapi:dashboard')  # Redirect to user_dashboard or home page
            else:
                messages.error(request, "Invalid email or password.")
    
    else:
        form = LoginForm()
    
    return render(request, "login.html", {"form": form})

def user_logout(request):
    # Log the user out
    logout(request)
    
    # Redirect to the login page or a landing page after logout
    return redirect('Hapi:login')  # You can change this to your desired page

@login_required
def user_dashboard(request):
    user = request.user
    fhir_id = user.fhir_id  
    
    fhir_data = get_fhir_data(fhir_id, user.role)
    print(fhir_id)
    if fhir_data:
        # Pass the FHIR data to the template
        return render(request, 'dashboard.html', {'fhir_data': fhir_data})
    else:
        # If FHIR data is not found, you can handle the error gracefully
        return render(request, 'dashboard.html', {'error': 'No FHIR data found.'})
    
def doctor_profile(request):
    if not request.user.is_authenticated:
        return redirect('Hapi:login')
    
    if request.user.role == 'patient':
        logout(request)
        return redirect('Hapi:login')
    
    user = request.user

    # Fetch existing PractitionerRole
    response = requests.get(f"{FHIR_SERVER_URL}/PractitionerRole?practitioner=Practitioner/{user.fhir_id}")
    
    role_data = {}
    if response.status_code == 200 and "entry" in response.json():
        role_data = response.json()["entry"][0]["resource"]
    print(role_data, user.fhir_id, user.role)
    if request.method == "POST":
        # Collect form data
        new_active = request.POST.get("active") == "on"
        new_organization = request.POST.get("organization")
        new_role_code = request.POST.get("role_code")
        new_specialties = request.POST.getlist("specialty")
        new_locations = request.POST.getlist("location")
        new_services = request.POST.getlist("healthcareService")
        new_phone = request.POST.get("phone")
        new_email = request.POST.get("email")
        new_available_days = request.POST.getlist("available_days")
        new_available_start = request.POST.get("available_start")
        new_available_end = request.POST.get("available_end")

        # Prepare the PractitionerRole resource
        practitioner_role = {
            "resourceType": "PractitionerRole",
            "practitioner": {"reference": f"Practitioner/{user.fhir_id}"},
            "active": new_active,
            "organization": {"display": new_organization},
            "code": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0286", "code": new_role_code}]}],
            "specialty": [{"text": spec} for spec in new_specialties],
            "location": [{"display": loc} for loc in new_locations],
            "healthcareService": [{"display": service} for service in new_services],
            "contact": [{"telecom": [{"system": "phone", "value": new_phone, "use": "work"}, {"system": "email", "value": new_email, "use": "work"}]}],
            "availability": {
                "availableTime": [{
                    "daysOfWeek": new_available_days,
                    "availableStartTime": new_available_start,
                    "availableEndTime": new_available_end
                }]
            },
        }

        # If PractitionerRole exists, update it
        if role_data:
            role_id = role_data["id"]
            requests.put(f"{FHIR_SERVER_URL}/PractitionerRole/{role_id}", json=practitioner_role)
        else:
            res = requests.post(f"{FHIR_SERVER_URL}/PractitionerRole", json=practitioner_role)
            print(res.status_code, practitioner_role)

        return redirect("Hapi:doctor_profile")

    return render(request, "doctor_profile.html", {"role_data": role_data})