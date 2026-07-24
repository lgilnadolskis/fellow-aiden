import streamlit as st
from fellow_aiden import FellowAiden
from fellow_aiden.profile import CoffeeProfile
from brew_recommendation import build_brew_recommendation
from openai import OpenAI

SYSTEM = """
Assume the role of a master coffee brewer. You focus exclusively on the pour over method and specialty coffee only. You often work with single origin coffees, but you also experiment with blends. Your recipes are executed by a robot, not a human, so maximum precision can be achieved. Temperatures are all maintained and stable in all steps. Always lead with the recipe, and only include explanations below that text, NOT inline. Below are the components of a recipe. 

Core brew settings: These settings are static and must match for single and batch brew.
Title: An interesting and creative name based on the coffee details. 
Ratio: How much coffee per water. Values MUST be between 14 and 20 with 0.5 step increments.
Bloom ratio: Water to use in bloom stage. Values MUST be between 1 and 3 with 0.5 step increments.
Bloom time: How long the bloom phase should last. Values MUST be between 1 and 120 seconds.
Bloom temperature: Temperature of the water. Values MUST be between 50 and 99 celsius.

Pulse settings: These are independent and can vary for single and batch brews. 
Number of pulses: Steps in which water is poured over coffee. Values MUST be between 1 and 10.
Time between pulses: Time in between each pulse. Values MUST be between 5 and 60 seconds. This MUST be included even if a single pulse is performed. 
Pulse temperate. Independent temperature to use for a given pulse.  Values MUST be between 50 and 99 celsius.

Below is an example of a previous recipe you put together for a speciality coffee called "Fruit cake" where you tasted cinnamon sugar, baked apples, and blackberry compote.

Roast: Light - Medium
Process | Cinnamon co-ferment | Strawberry co-ferment | Washed
33% Esteban Zamora - Cinnamon Anaerobic (San Marcos, Tarrazu, Costa Rica)
33% Sebastián Ramirez - Red Fruits (Quindio, Colombia)
33% Gamatui - Washed (Kapchorwa, Mt. Elgon, Uganda)

CORE
Ratio: 16
Bloom ratio: 3
Bloom time: 60s
Bloom temp: 87.5°C

SINGLE SERVE
Pulse 1 temp: 95°C
Pulse 2 temp: 92.5°C
Time between pulses: 25s
Number of pulses: 2 

BATCH
Pulse 1 temp: 95°C
Pulse 2 temp: 92.5°C
Time between pulses: 25s
Number of pulses: 2 

Here's another example. This coffee is a bold and intense cup composed of a smooth blend of Burundian and Latin American coffees with notes of mulled wine, baker's chocolate, blood orange, and a delicious blast of fudge.

Roast: Light - Medium
Process: Natural and Washed
Region: Burundi, Honduras and Peru
CORE
Ratio: 16
Bloom ratio: 2.5  
Bloom time: 30s
Bloom temp: 93.5°C 

SINGLE SERVE
Pulse 1 temp: 92°C
Pulse 2 temp: 92°C
Pulse 3 temp: 90.5°C 
Time between pulses: 20s
Number of pulses: 3 

BATCH
Pulse temp: 92°C 
Number of pulses: 1
"""    

REFORMAT_SYSTEM = """
Assume the role of a data engineer. You need to parse coffee recipes and their explanations so the data can be structured. Below are the important components of the recipe.

Core brew settings: These settings are static and must match for single and batch brew.
Title: An interesting and creative name based on the coffee details. 
Ratio: How much coffee per water. Values range from 1:14 to 1:20 with 0.5 steps.
Bloom ratio: Water to use in bloom stage. Values range from 1 to 3 with 0.5 steps.
Bloom time: How long the bloom phase should last. Values range from 1 to 120 seconds.
Bloom temperature: Temperature of the water. Values range from 50 celsius to 99 celsius.

Pulse settings: These are independent and can vary for single and batch brews. 
Number of pulses: Steps in which water is poured over coffee. Values range from 1 to 10.
Time between pulses: Time in between each pulse. Values range from 5 to 60 seconds. This must be included even if a single pulse is performed. 
Pulse temperate. Independent temperature to use for a given pulse.  Values range from 50 celsius to 99 celsius. 
"""


# ------------------------------------------------------------------------------
# Mock / Placeholder functions
# ------------------------------------------------------------------------------
def connect_to_coffee_brewer(email, password):
    """Mock function returning a list of profile dicts."""
    email = email.strip()
    password = password.strip()

    if 'aiden' not in st.session_state:
        try:
            local = FellowAiden(email, password)
        except Exception as e:
            if "incorrect" in str(e):
                return False
        st.session_state['aiden'] = local

    obj = {
        'device_settings': {
            'name': st.session_state['aiden'].get_display_name(),
        },
        # Make sure each profile has "description" if your mock doesn't already:
        'profiles': [
            {
                **p,
                **{"description": p.get("description", "")}
            }
            for p in st.session_state['aiden'].get_profiles()
        ]
    }
    return obj

def save_profile_to_coffee_machine(profile_name, updated_profile):
    st.success(f"Profile '{profile_name}' saved.")
    if 'description' in updated_profile:
        updated_profile.pop('description', None)
    if 'calculations' in updated_profile:
        updated_profile.pop('calculations', None)
    updated_profile['profileType'] = 0
    
    try:
        # Check if a profile with this name already exists
        existing_profile = st.session_state['aiden'].get_profile_by_title(profile_name)
        
        if existing_profile:
            # If profile exists, update it
            profile_id = existing_profile['id']
            st.session_state['aiden'].update_profile(profile_id, updated_profile)
        else:
            # If profile doesn't exist, create a new one
            st.session_state['aiden'].create_profile(updated_profile)
    except Exception as e:
        st.warning(f"Failed to save profile: {e}")

def parse_brewlink(link):
    """Returns a dict with all profile fields parsed from the link."""
    parsed = st.session_state['aiden'].parse_brewlink_url(link)
    # Add a 'description' key if not present:
    if 'description' not in parsed:
        parsed['description'] = ""
    return parsed


def extract_recipe_from_description(model_explanation):
    """Extracts the recipe from the description."""
    try:
        completion = st.session_state['oai'].beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": REFORMAT_SYSTEM},
                {"role": "user", "content": model_explanation},
            ],
            response_format=CoffeeProfile,
        )
        model_recipe = completion.choices[0].message.parsed
    except Exception as e:
        print("Failed to extract recipe from description:", e)
        return False
    
    return model_recipe


def generate_ai_recipe_and_explanation(USER, brew_water_ml=180):
    guidance = "Suggest a recipe for the following coffee. Provide your explanations below the recipe.\n"
    USER = ' '.join([guidance, USER])
    completion = st.session_state['oai'].chat.completions.create(
        model="o1-preview",
        messages=[
            {"role": "user", "content": SYSTEM + USER},
        ]
    )
    model_explanation = completion.choices[0].message.content
    print(model_explanation)

    while True:
        model_recipe = extract_recipe_from_description(model_explanation)
        if model_recipe:
            break

    recipe = model_recipe.model_dump()
    recipe['description'] = model_explanation
    recipe['calculations'] = build_brew_recommendation(brew_water_ml, recipe['ratio'])
    recipe['calculations']['brew_water_ml'] = brew_water_ml
    return recipe


def get_share_link(title):
    profile = st.session_state['aiden'].get_profile_by_title(title)
    return st.session_state['aiden'].generate_share_link(profile['id'])

# ------------------------------------------------------------------------------
# Streamlit Setup
# ------------------------------------------------------------------------------
st.set_page_config(layout="wide")

st.markdown(
    """
    <style>
    hr { 
        margin: 0em;
        border-width: 2px;
    }
    </style>
""",
    unsafe_allow_html=True,
)

if "brewer_settings" not in st.session_state:
    st.session_state.brewer_settings = None

if "new_profile" not in st.session_state:
    st.session_state.new_profile = None

if "selected_profile_index" not in st.session_state:
    st.session_state.selected_profile_index = None

# ------------------------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------------------------
with st.sidebar:
    st.header("Fellow Email Address")
    email = st.text_input(" ", placeholder="Enter your email", 
                          key="email", label_visibility="collapsed")

    st.header("Fellow Password")
    password = st.text_input(" ", placeholder="Enter your password", 
                             type="password", key="password", label_visibility="collapsed")

    # Connect button
    if st.button("Connect"):
        if email and password:
            result = connect_to_coffee_brewer(email, password)
            if not result:
                st.warning("Incorrect email or password.")
            st.session_state.brewer_settings = result
        else:
            st.warning("Please enter email and password first.")

    st.markdown("---")

    # If connected, show device info and profile management
    if st.session_state.brewer_settings:
        st.markdown("**New Profile from Brew Link**")

        brew_link = st.text_input(
            "Brew Link",
            placeholder="Paste brew link here...",
            key="brew_link"
        )
        
        # Create profile from brew link
        if st.button("Create Profile from Brew Link"):
            # 1. Parse the new data
            new_profile_data = parse_brewlink(brew_link)
            
            # 2. Clear out old "new_*" keys
            for key in list(st.session_state.keys()):
                if key.startswith("new_"):
                    del st.session_state[key]
            
            # 3. Set the brand-new profile
            st.session_state.new_profile = new_profile_data
            
            # 4. Clear out existing profile selection
            st.session_state.selected_profile_index = None
            st.session_state.selected_profile_choice = "— None —"

        st.markdown("---")

        # ---- AI BARISTA SECTION ----
        st.markdown("### AI Barista")
        st.markdown("#### OpenAI API Key")
        openai_api_key = st.text_input(" ", placeholder="Enter your OpenAI API Key", 
                                    type="password", key="openai_api_key", label_visibility="collapsed")
        brew_water_ml = st.number_input(
            "Brew water (ml)",
            min_value=150,
            max_value=1500,
            value=180,
            step=10,
            key="ai_brew_water_ml",
        )
        user_coffee_request = st.text_area(
            "Describe your coffee:",
            placeholder="Light roasted blend of washed (Sidama, Ethiopia) and gesha (Santa Barbara, Honduras) coffees",
            key="ai_barista_input"
        )

        openai_api_key = openai_api_key.strip()
        if st.button("Generate AI Profile", key="ai_barista_button"):
            if openai_api_key.strip():
                st.session_state['oai'] = OpenAI(api_key=openai_api_key)
                if user_coffee_request.strip():

                    try:
                        new_profile_data = generate_ai_recipe_and_explanation(user_coffee_request, brew_water_ml)
                    except Exception as e:
                        st.warning(f"Failed to generate AI recipe: {e}")
                        new_profile_data = None
                    
                    # 2. Clear out old "new_*" keys
                    for key in list(st.session_state.keys()):
                        if key.startswith("new_"):
                            del st.session_state[key]
                    
                    # 3. Set the brand-new profile
                    st.session_state.new_profile = new_profile_data
                    
                    # 4. Clear out existing profile selection
                    st.session_state.selected_profile_index = None
                    st.session_state.selected_profile_choice = "— None —"

                else:
                    st.warning("Please enter a description first.")
            else:
                st.warning("Please enter an OpenAI key first.")

        st.markdown("---")

        # ---- Existing Profiles ----
        st.markdown("**Existing Profiles**")
        profiles = st.session_state.brewer_settings["profiles"]
        titles = [p["title"] for p in profiles]

        choice = st.selectbox(
            "Select a Profile", 
            ["— None —"] + titles, 
            key="selected_profile_choice"
        )
        if choice != "— None —":
            st.session_state.selected_profile_index = titles.index(choice)
            st.session_state.new_profile = None
        else:
            st.session_state.selected_profile_index = None

        st.markdown("---")     
        device_info = st.session_state.brewer_settings["device_settings"]
        st.markdown("**Connected Brewer Settings**")
        for k, v in device_info.items():
            st.write(f"**{k.replace('_', ' ').title()}**: {v}")
        if st.button("Dump Config"):
            st.write(st.session_state['aiden'].get_device_config())



# ------------------------------------------------------------------------------
# Helper: Profile Editor
# ------------------------------------------------------------------------------
def render_profile_editor(profile_dict, profile_key="existing"):
    """
    Renders the same set of sliders/checkboxes used for editing a profile,
    plus a text area for 'description'.
    """
    def ss_key(k):
        return f"{profile_key}_{k}"

    st.write("### Editing Profile")

    # Title
    st.session_state[ss_key("title")] = st.text_input(
        "Profile Title",
        value=profile_dict["title"],
        key=ss_key("title_input")
    )

    # Description (AI Explanation or user text)
    st.session_state[ss_key("description")] = st.text_area(
        "Description (auto-filled by AI Barista or manually edited):",
        value=profile_dict.get("description", ""),   # default to "" if missing
        key=ss_key("description_input"),
        height=100
    )

    calculations = profile_dict.get("calculations")
    if calculations:
        st.markdown("**Brew calculations**")
        st.json(calculations)

    # Save button
    if st.button("Save", key=ss_key("save_button")):
        updated_profile = {
            "profileType": profile_dict.get("profileType", "custom"),  
            "title": st.session_state[ss_key("title_input")],
            "description": st.session_state.get(ss_key("description_input"), profile_dict.get("description", "")),
            "ratio": st.session_state.get(ss_key("ratio"), profile_dict.get("ratio", 16.0)),
            "bloomRatio": st.session_state.get(ss_key("bloomRatio"), profile_dict.get("bloomRatio", 2.0)),
            "bloomDuration": st.session_state.get(ss_key("bloomDuration"), profile_dict.get("bloomDuration", 30)),
            "bloomTemperature": st.session_state.get(ss_key("bloomTemperature"), profile_dict.get("bloomTemperature", 93.0)),
            "bloomEnabled": st.session_state.get(ss_key("bloomEnabled"), profile_dict.get("bloomEnabled", True)),
            "ssPulsesEnabled": st.session_state.get(ss_key("ssPulsesEnabled"), profile_dict.get("ssPulsesEnabled", False)),
            "ssPulsesNumber": st.session_state.get(ss_key("ssPulsesNumber"), profile_dict.get("ssPulsesNumber", 1)),
            "ssPulsesInterval": st.session_state.get(ss_key("ssPulsesInterval"), profile_dict.get("ssPulsesInterval", 10)),
            "ssPulseTemperatures": st.session_state.get(ss_key("ssPulseTemperatures"), profile_dict.get("ssPulseTemperatures", [93])),
            "batchPulsesEnabled": st.session_state.get(ss_key("batchPulsesEnabled"), profile_dict.get("batchPulsesEnabled", False)),
            "batchPulsesNumber": st.session_state.get(ss_key("batchPulsesNumber"), profile_dict.get("batchPulsesNumber", 1)),
            "batchPulsesInterval": st.session_state.get(ss_key("batchPulsesInterval"), profile_dict.get("batchPulsesInterval", 10)),
            "batchPulseTemperatures": st.session_state.get(ss_key("batchPulseTemperatures"), profile_dict.get("batchPulseTemperatures", [93])),
        }
        # print(updated_profile)
        save_profile_to_coffee_machine(updated_profile["title"], updated_profile)

        # Overwrite the original dict so we see changes right away
        for k, v in updated_profile.items():
            profile_dict[k] = v

    if st.button("Share", key=ss_key("share_button")):
        link = get_share_link(profile_dict["title"])
        if link:
            st.write(f"**Share Link**: {link}")

    # Bloom
    bloom_enabled = st.checkbox(
        "Enable Bloom?",
        value=profile_dict.get("bloomEnabled", True),
        key=ss_key("bloomEnabled")
    )
    ratio = st.slider(
        "Ratio",
        14.0, 20.0, step=0.5,
        value=float(profile_dict.get("ratio", 16.0)),
        key=ss_key("ratio")
    )

    if bloom_enabled:
        bloom_ratio = st.slider(
            "Bloom Ratio",
            1.0, 3.0, step=0.5,
            value=float(profile_dict.get("bloomRatio", 2.0)),
            key=ss_key("bloomRatio")
        )
        bloom_duration = st.slider(
            "Bloom Duration (seconds)",
            1, 120, step=1,
            value=profile_dict.get("bloomDuration", 30),
            key=ss_key("bloomDuration")
        )
        bloom_temp = st.slider(
            "Bloom Temperature (°C)",
            50.0, 99.0, step=0.5,
            value=float(profile_dict.get("bloomTemperature", 93.0)),
            key=ss_key("bloomTemperature")
        )
    else:
        st.write("Bloom is disabled.")

    st.markdown("---")
    # Single-Serve pulses
    ss_pulses_enabled = st.checkbox(
        "Enable Single-Serve Pulses?",
        value=profile_dict.get("ssPulsesEnabled", False),
        key=ss_key("ssPulsesEnabled")
    )
    ss_pulses_number = st.number_input(
        "Number of SS Pulses",
        min_value=1, max_value=10,
        value=profile_dict.get("ssPulsesNumber", 1),
        key=ss_key("ssPulsesNumber")
    )
    ss_pulses_interval = st.number_input(
        "Time between SS Pulses (sec)",
        min_value=1, max_value=60,
        value=profile_dict.get("ssPulsesInterval", 10),
        key=ss_key("ssPulsesInterval")
    )

    # Handle single-serve pulse temperatures
    if ss_key("ssPulseTemperatures") not in st.session_state:
        st.session_state[ss_key("ssPulseTemperatures")] = profile_dict.get("ssPulseTemperatures", [93])

    while len(st.session_state[ss_key("ssPulseTemperatures")]) < ss_pulses_number:
        st.session_state[ss_key("ssPulseTemperatures")].append(90)
    st.session_state[ss_key("ssPulseTemperatures")] = \
        st.session_state[ss_key("ssPulseTemperatures")][:ss_pulses_number]

    for i in range(ss_pulses_number):
        temp_key = f"{ss_key('ssTemp')}_{i}"
        st.session_state[ss_key("ssPulseTemperatures")][i] = st.slider(
            f"SS Pulse {i+1} Temperature (°C)",
            min_value=50.0, max_value=99.0, step=0.5,
            value=float(st.session_state[ss_key("ssPulseTemperatures")][i]),
            key=temp_key
        )

    st.markdown("---")
    # Batch pulses
    batch_pulses_enabled = st.checkbox(
        "Enable Batch Pulses?",
        value=profile_dict.get("batchPulsesEnabled", False),
        key=ss_key("batchPulsesEnabled")
    )
    batch_pulses_number = st.number_input(
        "Number of Batch Pulses",
        min_value=1, max_value=10,
        value=profile_dict.get("batchPulsesNumber", 1),
        key=ss_key("batchPulsesNumber")
    )
    batch_pulses_interval = st.number_input(
        "Time between Batch Pulses (sec)",
        min_value=1, max_value=60,
        value=profile_dict.get("batchPulsesInterval", 10),
        key=ss_key("batchPulsesInterval")
    )

    if ss_key("batchPulseTemperatures") not in st.session_state:
        st.session_state[ss_key("batchPulseTemperatures")] = profile_dict.get("batchPulseTemperatures", [93])

    while len(st.session_state[ss_key("batchPulseTemperatures")]) < batch_pulses_number:
        st.session_state[ss_key("batchPulseTemperatures")].append(90)
    st.session_state[ss_key("batchPulseTemperatures")] = \
        st.session_state[ss_key("batchPulseTemperatures")][:batch_pulses_number]

    for i in range(batch_pulses_number):
        temp_key = f"{ss_key('batchTemp')}_{i}"
        st.session_state[ss_key("batchPulseTemperatures")][i] = st.slider(
            f"Batch Pulse {i+1} Temperature (°C)",
            min_value=50.0, max_value=99.0, step=0.5,
            value=float(st.session_state[ss_key("batchPulseTemperatures")][i]),
            key=temp_key
        )

# ------------------------------------------------------------------------------
# Main Page Layout
# ------------------------------------------------------------------------------
if st.session_state.new_profile:
    # Render the newly created profile from Brew Link or AI Barista
    render_profile_editor(st.session_state.new_profile, profile_key="new")
elif st.session_state.selected_profile_index is not None:
    # Render an existing profile
    idx = st.session_state.selected_profile_index
    p_data = st.session_state.brewer_settings["profiles"][idx]
    render_profile_editor(p_data, profile_key=f"existing_{idx}")
else:
    st.write("No profile selected or created.")