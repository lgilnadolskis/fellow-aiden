#!/usr/bin/env python3
"""
Script to list all coffee profiles and schedules from Fellow Aiden machine.
Prints them to console and exports to CSV files.
"""
import os
import csv
import json
from datetime import timedelta
from fellow_aiden import FellowAiden


def seconds_to_time(seconds):
    """Convert seconds from start of day to HH:MM:SS format."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def days_to_string(days_list):
    """Convert boolean list of days to readable string."""
    day_names = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    active_days = [day_names[i] for i, active in enumerate(days_list) if active]
    return ', '.join(active_days) if active_days else 'None'


def print_profiles(profiles):
    """Print profiles in a readable format."""
    print("\n" + "="*80)
    print(f"{'COFFEE PROFILES':^80}")
    print("="*80)
    print(f"\nTotal Profiles: {len(profiles)}\n")
    
    for idx, profile in enumerate(profiles, 1):
        print(f"\n--- Profile {idx}: {profile.get('title', 'Untitled')} ---")
        print(f"  ID: {profile.get('id', 'N/A')}")
        print(f"  Ratio: 1:{profile.get('ratio', 'N/A')}")
        print(f"  Bloom: {'Enabled' if profile.get('bloomEnabled') else 'Disabled'}")
        
        if profile.get('bloomEnabled'):
            print(f"    - Bloom Ratio: {profile.get('bloomRatio', 'N/A')}")
            print(f"    - Bloom Duration: {profile.get('bloomDuration', 'N/A')}s")
            print(f"    - Bloom Temperature: {profile.get('bloomTemperature', 'N/A')}°C")
        
        # Single Serve Pulses
        if profile.get('ssPulsesEnabled'):
            print(f"  Single Serve Pulses: Enabled")
            print(f"    - Number of Pulses: {profile.get('ssPulsesNumber', 'N/A')}")
            print(f"    - Interval: {profile.get('ssPulsesInterval', 'N/A')}s")
            temps = profile.get('ssPulseTemperatures', [])
            if temps:
                print(f"    - Temperatures: {', '.join([f'{t}°C' for t in temps])}")
        else:
            print(f"  Single Serve Pulses: Disabled")
        
        # Batch Pulses
        if profile.get('batchPulsesEnabled'):
            print(f"  Batch Pulses: Enabled")
            print(f"    - Number of Pulses: {profile.get('batchPulsesNumber', 'N/A')}")
            print(f"    - Interval: {profile.get('batchPulsesInterval', 'N/A')}s")
            temps = profile.get('batchPulseTemperatures', [])
            if temps:
                print(f"    - Temperatures: {', '.join([f'{t}°C' for t in temps])}")
        else:
            print(f"  Batch Pulses: Disabled")
        
        # Additional info if available
        if profile.get('lastUsedTime'):
            print(f"  Last Used: {profile.get('lastUsedTime')}")
        if profile.get('isDefaultProfile'):
            print(f"  Default Profile: Yes")
    
    print("\n" + "="*80 + "\n")


def print_schedules(schedules):
    """Print schedules in a readable format."""
    print("\n" + "="*80)
    print(f"{'BREW SCHEDULES':^80}")
    print("="*80)
    print(f"\nTotal Schedules: {len(schedules)}\n")
    
    if not schedules:
        print("  No schedules configured.\n")
    else:
        for idx, schedule in enumerate(schedules, 1):
            status = "ENABLED" if schedule.get('enabled') else "DISABLED"
            print(f"\n--- Schedule {idx} [{status}] ---")
            print(f"  ID: {schedule.get('id', 'N/A')}")
            print(f"  Time: {seconds_to_time(schedule.get('secondFromStartOfTheDay', 0))}")
            print(f"  Days: {days_to_string(schedule.get('days', []))}")
            print(f"  Water Amount: {schedule.get('amountOfWater', 'N/A')}ml")
            print(f"  Profile ID: {schedule.get('profileId', 'N/A')}")
    
    print("\n" + "="*80 + "\n")


def save_profiles_to_csv(profiles, filename='profiles.csv'):
    """Save profiles to CSV file."""
    if not profiles:
        print("No profiles to save.")
        return
    
    # Define the fields we want to export
    fieldnames = [
        'id', 'title', 'ratio', 'bloomEnabled', 'bloomRatio', 'bloomDuration', 
        'bloomTemperature', 'ssPulsesEnabled', 'ssPulsesNumber', 'ssPulsesInterval',
        'ssPulseTemperatures', 'batchPulsesEnabled', 'batchPulsesNumber', 
        'batchPulsesInterval', 'batchPulseTemperatures', 'isDefaultProfile',
        'lastUsedTime', 'createdAt'
    ]
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        
        for profile in profiles:
            # Convert lists to strings for CSV
            row = profile.copy()
            if 'ssPulseTemperatures' in row and isinstance(row['ssPulseTemperatures'], list):
                row['ssPulseTemperatures'] = json.dumps(row['ssPulseTemperatures'])
            if 'batchPulseTemperatures' in row and isinstance(row['batchPulseTemperatures'], list):
                row['batchPulseTemperatures'] = json.dumps(row['batchPulseTemperatures'])
            writer.writerow(row)
    
    print(f"✓ Profiles saved to {filename}")


def save_schedules_to_csv(schedules, filename='schedules.csv'):
    """Save schedules to CSV file."""
    if not schedules:
        print("No schedules to save.")
        return
    
    fieldnames = [
        'id', 'enabled', 'time', 'days', 'days_readable',
        'amountOfWater', 'profileId', 'createdAt'
    ]
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        
        for schedule in schedules:
            row = schedule.copy()
            # Add human-readable time
            row['time'] = seconds_to_time(schedule.get('secondFromStartOfTheDay', 0))
            # Add both raw days array and readable format
            if 'days' in row and isinstance(row['days'], list):
                row['days_readable'] = days_to_string(row['days'])
                row['days'] = json.dumps(row['days'])
            writer.writerow(row)
    
    print(f"✓ Schedules saved to {filename}")


def main():
    """Main function to retrieve and display profiles and schedules."""
    print("\n" + "="*80)
    print(f"{'FELLOW AIDEN - PROFILES & SCHEDULES EXPORTER':^80}")
    print("="*80 + "\n")
    
    # Get credentials from environment variables or prompt
    email = os.environ.get('FELLOW_EMAIL')
    password = os.environ.get('FELLOW_PASSWORD')
    
    if not email:
        email = input("Enter your Fellow account email: ").strip()
    if not password:
        import getpass
        password = getpass.getpass("Enter your Fellow account password: ").strip()
    
    try:
        print("\nConnecting to Fellow Aiden...")
        aiden = FellowAiden(email, password)
        print(f"✓ Connected to: {aiden.get_display_name()}")
        
        # Get profiles
        print("\nRetrieving profiles...")
        profiles = aiden.get_profiles()
        print(f"✓ Retrieved {len(profiles)} profiles")
        
        # Get schedules
        print("Retrieving schedules...")
        schedules = aiden.get_schedules()
        print(f"✓ Retrieved {len(schedules)} schedules")
        
        # Print to console
        print_profiles(profiles)
        print_schedules(schedules)
        
        # Save to CSV
        print("\nExporting to CSV files...")
        save_profiles_to_csv(profiles, 'profiles.csv')
        save_schedules_to_csv(schedules, 'schedules.csv')
        
        print("\n✓ Export complete!")
        print("\nFiles created:")
        print("  - profiles.csv")
        print("  - schedules.csv")
        print("\n" + "="*80 + "\n")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        print("Please check your credentials and try again.\n")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
