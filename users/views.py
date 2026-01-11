from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import UserRegisterForm, ProfileUpdateForm
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.conf import settings
import random
from .models import Profile
from django.contrib.auth.models import User

def register(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            
            # Generate OTP
            otp = str(random.randint(100000, 999999))
            user.profile.verification_code = otp
            user.profile.save()
            
            # Send Email
            subject = 'Verify your Diamond Chat Account'
            message = f'Hi {username},\n\nYour verification code is: {otp}\n\nWelcome to Diamond Chat!'
            email_from = settings.EMAIL_HOST_USER if hasattr(settings, 'EMAIL_HOST_USER') else 'noreply@diamondchat.com'
            recipient_list = [form.cleaned_data.get('email')]
            
            # --- BYPASSING EMAIL FOR DEPLOYMENT TESTING ---
            # try:
            #     send_mail(subject, message, email_from, recipient_list)
            #     request.session['verification_user_id'] = user.id
            #     messages.info(request, f'Verification code sent to email! (Check Terminal)')
            #     return redirect('verify_email')
            # except Exception as e:
            #     messages.error(request, f'Error sending email: {e}')
            #     return redirect('register')
            
            # Auto-verify directly
            user.profile.is_verified = True
            user.profile.save()
            messages.success(request, 'Account created! (Email verification skipped for testing)')
            return redirect('login')

    else:
        form = UserRegisterForm()
    return render(request, 'users/register.html', {'form': form})


def verify_email(request):
    if request.method == 'POST':
        otp = request.POST.get('otp')
        user_id = request.session.get('verification_user_id')
        
        if not user_id:
            messages.error(request, 'Session expired. Please register again.')
            return redirect('register')
            
        try:
            profile = Profile.objects.get(user_id=user_id)
            if profile.verification_code == otp:
                profile.is_verified = True
                profile.verification_code = None # Clear code
                profile.save()
                
                # Cleanup session
                del request.session['verification_user_id']
                
                messages.success(request, 'Email verified! You can now log in.')
                return redirect('login')
            else:
                messages.error(request, 'Invalid Code. Please try again.')
        except Profile.DoesNotExist:
            messages.error(request, 'User not found.')
            return redirect('register')
            
    return render(request, 'users/verify_email.html')


from django.views.decorators.cache import never_cache

@login_required
@never_cache
def dashboard(request):
    from django.utils import timezone
    from datetime import timedelta
    # from .models import Profile # Already imported at top
    from .context_processors import inbox_count 

    # Calculate active users (seen in last 5 minutes)
    five_min_ago = timezone.now() - timedelta(minutes=5)
    online_count = Profile.objects.filter(last_seen__gte=five_min_ago).count()



    # Verification Check
    if not request.user.profile.is_verified:
        messages.warning(request, 'Please verify your email to access the dashboard.')
        return redirect('verify_email')

    return render(request, 'users/dashboard.html', {'online_count': online_count})

from django.http import JsonResponse
import pycountry

def get_states(request):
    country_code = request.GET.get('country')
    if not country_code:
        return JsonResponse({'states': []})
    
    try:
        # Get subdivisions (states) for the country
        subdivisions = pycountry.subdivisions.get(country_code=country_code)
        if subdivisions:
            states = [{'code': sub.code, 'name': sub.name} for sub in subdivisions]
            # Sort by name
            states.sort(key=lambda x: x['name'])
            return JsonResponse({'states': states})
    except Exception as e:
        print(f"Error fetching states: {e}")
        
    return JsonResponse({'states': []})


@login_required
def profile(request):
    if request.method == 'POST':
        p_form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user.profile)
        if p_form.is_valid():
            p_form.save()
            messages.success(request, f'Your account has been updated!')
            return redirect('dashboard')
        else:
            print(p_form.errors) # DEBUG
    else:
        p_form = ProfileUpdateForm(instance=request.user.profile)

    context = {
        'p_form': p_form
    }

    return render(request, 'users/profile.html', context)

from django.views.decorators.csrf import csrf_exempt
import json
from .models import Report

@login_required
def verify_gender(request):
    if request.method == 'POST':
        import json
        try:
            data = json.loads(request.body)
            print(f"DEBUG: verify_gender called by {request.user.username} with data: {data}")
        except json.JSONDecodeError:
            print("DEBUG: JSON Decode Error")
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'})

        target_username = data.get('username')
        gender_verdict = data.get('gender') # 'M' or 'F'

        if not target_username or not gender_verdict:
            print("DEBUG: Missing username or gender")
            return JsonResponse({'status': 'error', 'message': 'Invalid data'})

        try:
            target_user = User.objects.get(username=target_username)
            if target_user == request.user:
                 print("DEBUG: User tried to verify self")
                 return JsonResponse({'status': 'error', 'message': 'Cannot verify yourself'})
            
            # --- VOTING LOGIC ---
            profile = target_user.profile
            print(f"DEBUG: Before vote - M:{profile.male_votes} F:{profile.female_votes}")
            
            if gender_verdict == 'M':
                profile.male_votes += 1
            elif gender_verdict == 'F':
                profile.female_votes += 1
            
            # Majority Rule (DECOUPLED: Does NOT update profile.gender anymore)
            # if profile.male_votes > profile.female_votes:
            #     profile.gender = 'M'
            # elif profile.female_votes > profile.male_votes:
            #     profile.gender = 'F'
            
            profile.save()
            print(f"DEBUG: After vote - M:{profile.male_votes} F:{profile.female_votes} (Gender Remains: {profile.gender})")

            return JsonResponse({
                'status': 'success', 
                'message': 'Vote recorded',
                'new_gender': profile.gender
            })
        except User.DoesNotExist:
             print(f"DEBUG: Target user {target_username} not found")
             return JsonResponse({'status': 'error', 'message': 'User not found'})
    
    return JsonResponse({'status': 'error', 'message': 'POST required'})

@login_required
def report_user(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            reported_username = data.get('username')
            reason = data.get('reason', 'Inappropriate Behavior')
            
            # Find the user being reported
            try:
                from django.contrib.auth.models import User
                reported_user = User.objects.get(username=reported_username)
            except User.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'User not found'})

            # Create Report
            Report.objects.create(
                reporter=request.user,
                reported_user=reported_user,
                reason=reason
            )

            # Update Profile Stats
            profile = reported_user.profile
            profile.reports_received += 1
            
            # Auto-Ban Logic
            if profile.reports_received >= 3:
                profile.is_banned = True
                print(f"BANNED USER: {reported_username}") # Log it
            
            profile.save()
            
            return JsonResponse({'status': 'success', 'banned': profile.is_banned})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request'})

# --- TEMPORARY ADMIN CREATION VIEW ---
def create_superuser_temp(request):
    try:
        from django.contrib.auth.models import User
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
            return JsonResponse({'status': 'Data Created', 'msg': 'User: admin, Pass: admin123'})
        else:
            return JsonResponse({'status': 'Exists', 'msg': 'Admin already exists'})
    except Exception as e:
        return JsonResponse({'status': 'Error', 'msg': str(e)})