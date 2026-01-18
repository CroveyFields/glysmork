from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Loop
from room.models import Room
import uuid
from .models import Loop, CallRequest
from django.contrib.auth.models import User
from users.models import Profile
from django.views.decorators.cache import never_cache

@login_required
def start_search(request):
    user = request.user
    profile = user.profile
    
    if not profile.is_verified:
        return redirect('verify_email')

    # 1. Check if user has enough diamonds
    if profile.diamonds < 3:
        messages.error(request, "Not enough diamonds! You need 3 diamonds.")
        return redirect('dashboard')
    
    # 2. Check Age Restriction
    if profile.age < 18:
        messages.error(request, "You must be 18+ to use this feature.")
        return redirect('dashboard')

    # Remove ANY existing stale entry for this user in the queue
    Loop.objects.filter(user=user).delete()

    # 2. Determine target gender
    target_gender = 'F' if profile.gender == 'M' else 'M'
    
    # 3. Search the "Queue" (Loop) for a waiting user
    match = Loop.objects.select_related('user__profile').filter(gender=target_gender).first()

    if match:
        # --- FOUND A MATCH! ---
        
        # A. Create a new unique room
        room_name = str(uuid.uuid4())[:8]
        new_room = Room.objects.create(name=room_name)
        
        # B. Add both users to the room
        new_room.users.add(user)
        new_room.users.add(match.user)
        
        # C. Remove the matched user from the Queue
        match.delete()
        
        # D. Deduct Diamonds from BOTH
        profile.diamonds -= 3
        profile.save()
        
        other_profile = match.user.profile
        other_profile.diamonds -= 3
        other_profile.save()
        
        # E. Redirect to the Room
        request.session['is_waiting'] = False
        return redirect('rooms', room_name=room_name)

    else:
        # --- NO MATCH FOUND (YET) ---
        
        # Check if already in queue to avoid duplicates
        if not Loop.objects.filter(user=user).exists():
            Loop.objects.create(user=user, gender=profile.gender)
            
        # Set session flag to indicate we are actively waiting
        request.session['is_waiting'] = True
        return redirect('waiting_page')

@login_required
@never_cache
def waiting_page(request):
    # Ensure the user is actually supposed to be waiting
    if not request.session.get('is_waiting', False):
        return redirect('dashboard')
        
    return render(request, 'matchmaking/waiting.html')

@login_required
def cancel_search(request):
    Loop.objects.filter(user=request.user).delete()
    request.session['is_waiting'] = False
    return redirect('dashboard')


from django.http import JsonResponse

# ... existing code ...

@login_required
@never_cache
def check_match_status(request):
    # STRICT SESSION CHECK: If the user didn't start a search recently, ignore everything.
    if not request.session.get('is_waiting', False):
        return JsonResponse({'status': 'cancelled'})

    from django.utils import timezone
    from datetime import timedelta

    # Check if the user has been added to a Room recently (last 30 seconds)
    thirty_seconds_ago = timezone.now() - timedelta(seconds=30)
    
    # We sort by ID desc to get the newest room, AND filter by creation time
    latest_room = request.user.rooms.filter(created_at__gte=thirty_seconds_ago).order_by('-id').first()
    
    # Check if user is currently in the queue
    in_queue = Loop.objects.filter(user=request.user).exists()

    if latest_room and not in_queue:
        # Match confirmed! Clear the flag so they don't get redirected again later.
        request.session['is_waiting'] = False
        return JsonResponse({'status': 'matched', 'room_name': latest_room.name})
    
    if in_queue:
        return JsonResponse({'status': 'waiting'})

    # Fallback
    return JsonResponse({'status': 'cancelled'})



@login_required
def user_directory(request):
    from django.utils import timezone
    from datetime import timedelta
    
    if not request.user.profile.is_verified:
        return redirect('verify_email')

    if request.user.profile.age < 18:
        messages.error(request, "You must be 18+ to view the directory.")
        return redirect('dashboard')

    # Fix: Get filter parameters
    gender = request.GET.get('gender', '')
    min_age = request.GET.get('min_age', 18)
    max_age = request.GET.get('max_age', 100)
    location = request.GET.get('location', '')
    max_price = request.GET.get('max_price', 1000)

    # Fix: Filter in Database with DOUBLE underscore __
    users = Profile.objects.select_related('user').filter(
        call_price__gt=0
    ).exclude(user=request.user)

    # Filter for online users seen in last 5 min
    five_min_ago = timezone.now() - timedelta(minutes=5)
    users = users.filter(last_seen__gte=five_min_ago)

    if gender:
        users = users.filter(gender=gender)
    
    users = users.filter(age__gte=min_age, age__lte=max_age)
    
    if location:
        # Flexible Search: Check State OR Country Name
        from django.db.models import Q
        from django_countries import countries

        # Find country codes where key or name matches the search query
        matching_codes = []
        for code, name in list(countries):
            if location.lower() in name.lower() or location.upper() == code:
                matching_codes.append(code)

        users = users.filter(
            Q(state__icontains=location) | 
            Q(country__in=matching_codes) |
            Q(location__icontains=location) # Support legacy data
        )
    
    users = users.filter(call_price__lte=max_price)

    return render(request, 'matchmaking/directory.html', {
        'users': users,
        'filters': locals() # This passes all variables to template
    })

@login_required
def send_call_request(request, username):
    sender = request.user
    receiver = User.objects.get(username = username)

    existing_request = CallRequest.objects.filter(sender = sender, receiver = receiver, status = 'pending').exists()
    if existing_request:
        messages.warning(request, "You already sent a request to this user!" )

        return redirect('user_directory')


    cost = int(receiver.profile.call_price * 1.5)
    if sender.profile.diamonds < cost:
        messages.error(request, f"You need {cost} diamonds to call them.")
        return redirect("user_directory")


    CallRequest.objects.create(sender = sender, receiver = receiver)
    
    # --- NOTIFY RECEIVER ---
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"user_{receiver.id}",
        {
            "type": "notification_message",
            "message": "New Call Request!"
        }
    )

    messages.success(request, f"Request sent to {receiver.username}!")
    return redirect('user_directory')

@login_required
def inbox(request):
    if request.user.profile.age < 18:
        messages.error(request, "You must be 18+ to access the inbox.")
        return redirect('dashboard')

    requests = CallRequest.objects.filter(receiver = request.user, status = 'pending').order_by('-timestamp')
    return render(request, 'matchmaking/inbox.html', {'requests': requests})


@login_required
def handle_request(request, request_id, action):
    from django.db import transaction
    call_req = CallRequest.objects.select_related('sender__profile', 'receiver__profile').get(id = request_id)

    if call_req.status != 'pending':
        messages.warning(request, "This request has already been processed.")
        return redirect('inbox')

    if action == 'reject':
        call_req.status = 'rejected'
        call_req.save()
        messages.info(request, "Request rejected.")

    elif action == 'accept':
        with transaction.atomic():
            # Refetch to lock properly if we were doing select_for_update, 
            # but usually atomic + status check is enough for simple cases.
            
            caller = call_req.sender
            receiver = call_req.receiver

            price = receiver.profile.call_price
            total_cost = int(price * 1.5)

            # Check if caller is online
            if not caller.profile.is_online():
                messages.error(request, 'Caller is not online anymore!')
                return redirect('inbox')

            if caller.profile.diamonds < total_cost:
                messages.error(request, 'Caller ran out of diamonds !')
                call_req.status = 'rejected'
                call_req.save()
                return redirect('inbox')


            caller.profile.diamonds -= total_cost
            caller.profile.save()

            receiver.profile.diamonds += price
            receiver.profile.save()

            room_name = f"call_{uuid.uuid4().hex[:8]}"
            Room.objects.create(name = room_name).users.add(caller, receiver)


            call_req.status = 'accepted'
            call_req.room_name = room_name
            call_req.save()

        return redirect('rooms', room_name = room_name)

    return redirect('inbox')

@login_required
@never_cache
def check_request_status(request):
    # Log to file for debugging
    # with open("debug_match.txt", "a") as f:
    #    f.write(f"Checking status for {request.user.username}...\n")

    # Check for any ACCEPTED requests sent by this user
    accepted_req = CallRequest.objects.filter(sender=request.user, status='accepted').first()
    
    if accepted_req:
        room_name = accepted_req.room_name
        
        # with open("debug_match.txt", "a") as f:
        #    f.write(f" -> MATCH FOUND! Room: {room_name}\n")

        # Mark as connected
        accepted_req.status = 'connected'
        accepted_req.save()
        
        return JsonResponse({'status': 'accepted', 'room_name': room_name})
        
    return JsonResponse({'status': 'pending'})