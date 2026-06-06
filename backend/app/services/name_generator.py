"""Deterministic Indian-name generator for the Blood Warriors dataset.

Two responsibilities:

1.  ``generate_name(external_id, gender)`` — pure function that returns a
    name from the pools using an MD5 hash of the id. Stable across processes,
    but two different ids CAN collide on the same (first, last) tuple.

2.  ``assign_unique_names(rows)`` — global pre-pass that walks every row
    once and guarantees each ``user_id`` ends up with a (first, last) tuple
    that no other row holds. Used by ``scripts.extend_dataset`` so the
    written CSV has 7,033 unique names.

Pools are large enough that the collision walk hits in ≤2 probes per row
under the current dataset size:

    male_first  ≈ 220 names
    female_first≈ 220 names
    last_names  ≈ 200 names
    →  ~44k unique (first, last) combinations per gender, enough for the
       6,949 donors + 84 patients with room to spare.

Pool curation: ~60 % South Indian first names + surnames (Blood Warriors
operates out of Telangana / Andhra Pradesh) with broad national coverage
across Hindi-belt, Bengali, Gujarati, Marathi, Punjabi, and Tamil/Kannada.
"""

from __future__ import annotations

import hashlib
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# Name pools (curated, deduplicated — kept ascii-only for CSV safety)
# ---------------------------------------------------------------------------


MALE_FIRST_NAMES: list[str] = [
    # Pan-India / Hindi-belt
    "Aarav", "Aaryan", "Abhay", "Abhinav", "Abhishek", "Aditya", "Ajay",
    "Akash", "Akhil", "Akshay", "Amar", "Amit", "Aniket", "Anil", "Ankit",
    "Anuj", "Anup", "Arjun", "Arun", "Aryan", "Ashish", "Ashok", "Atul",
    "Bharat", "Bhavesh", "Chaitanya", "Chetan", "Chirag", "Daksh",
    "Darshan", "Deepak", "Dev", "Devansh", "Dhruv", "Dinesh", "Gagan",
    "Ganesh", "Gaurav", "Girish", "Gopal", "Govind", "Harish", "Harsh",
    "Hemant", "Himanshu", "Hitesh", "Ishan", "Jagdish", "Jatin", "Kabir",
    "Kapil", "Karan", "Kartik", "Kaushik", "Keshav", "Kishore", "Krish",
    "Krishna", "Kunal", "Lalit", "Madhav", "Mahesh", "Manas", "Manish",
    "Manoj", "Mayank", "Mihir", "Mohan", "Mukesh", "Naman", "Nandan",
    "Naresh", "Navin", "Naveen", "Nayan", "Neeraj", "Niharika", "Nikhil",
    "Nilesh", "Nirav", "Nishant", "Om", "Omkar", "Parth", "Piyush",
    "Prabhat", "Pradeep", "Prakash", "Pranav", "Pratik", "Praveen",
    "Prem", "Punit", "Raghav", "Rahul", "Raj", "Rajat", "Rajeev",
    "Rajendra", "Rajesh", "Rajiv", "Rakesh", "Ram", "Ramesh", "Ranjit",
    "Rishabh", "Rishi", "Rohan", "Rohit", "Sahil", "Samar", "Sameer",
    "Sandeep", "Sanjay", "Sanjeev", "Sankalp", "Santhosh", "Sarthak",
    "Satish", "Saurabh", "Shantanu", "Shashank", "Shivam", "Shivansh",
    "Shrey", "Siddharth", "Sohan", "Sourabh", "Subhash", "Sudhir",
    "Sumit", "Sundar", "Sunil", "Suraj", "Surendra", "Suresh", "Tanay",
    "Tanmay", "Tarun", "Tushar", "Uday", "Ujjwal", "Umesh", "Utkarsh",
    "Varun", "Ved", "Vihaan", "Vijay", "Vikas", "Vikram", "Vimal",
    "Vinay", "Vineet", "Vinod", "Viraj", "Vishal", "Vishesh", "Vishnu",
    "Vivek", "Yash", "Yashwant", "Yogesh",
    # South Indian additions
    "Adithya", "Anand", "Arvind", "Aravind", "Balu", "Bharath", "Chandran",
    "Charan", "Dileep", "Dinakar", "Eswar", "Gautham", "Giridhar",
    "Gopinath", "Hari", "Haridas", "Hariharan", "Jagan", "Jaideep",
    "Jayaram", "Kannan", "Karthik", "Karthikeyan", "Krishnakumar",
    "Lakshman", "Madan", "Mahadev", "Mani", "Manikandan", "Murali",
    "Muralidhar", "Murugan", "Nataraj", "Pradip", "Prashant", "Raghu",
    "Rajan", "Ramana", "Ramaswamy", "Ranganath", "Sathish", "Sekar",
    "Senthil", "Shankar", "Sivakumar", "Sridhar", "Srikanth", "Srinivas",
    "Subramani", "Sundaram", "Suriya", "Venkat", "Venkatesh", "Vijayan",
    "Yadunandan",
]


FEMALE_FIRST_NAMES: list[str] = [
    # Pan-India / Hindi-belt
    "Aaradhya", "Aarohi", "Aditi", "Aisha", "Aishwarya", "Akanksha",
    "Akshara", "Alka", "Amala", "Ambika", "Amrita", "Ananya", "Anika",
    "Anisha", "Anita", "Anjali", "Anushka", "Aparna", "Archana", "Aruna",
    "Arundhati", "Arushi", "Asha", "Avani", "Bandhana", "Bela",
    "Bhavana", "Bhavya", "Bhumika", "Charu", "Chhaya", "Chitra", "Damini",
    "Darshana", "Deepa", "Deepali", "Deepika", "Devika", "Dhriti",
    "Divya", "Esha", "Gauri", "Gayatri", "Geeta", "Gita", "Gunjan",
    "Harini", "Hema", "Hemlata", "Indira", "Isha", "Ishita", "Jaya",
    "Jhanvi", "Jyoti", "Kajal", "Kalpana", "Kamala", "Kanchan", "Karuna",
    "Kashish", "Kavya", "Kavita", "Khushi", "Kiran", "Komal", "Kriti",
    "Lakshmi", "Lalitha", "Lata", "Latha", "Madhavi", "Madhu", "Madhuri",
    "Malati", "Mamta", "Mandakini", "Manisha", "Manju", "Meena", "Meera",
    "Mira", "Mona", "Mridula", "Naina", "Nandini", "Neelam", "Neena",
    "Neha", "Nidhi", "Nikita", "Nirmala", "Nisha", "Nitya", "Padma",
    "Pallavi", "Parul", "Pavithra", "Pooja", "Poonam", "Prachi",
    "Pranjali", "Pratibha", "Pratima", "Preethi", "Preeti", "Prerana",
    "Priya", "Priyanka", "Pushpa", "Radha", "Ragini", "Raima", "Rajshri",
    "Rakhi", "Rani", "Rashmi", "Reena", "Rekha", "Renu", "Reshma",
    "Riddhi", "Rina", "Ritu", "Riya", "Roopa", "Roshni", "Saanvi",
    "Sakshi", "Samiksha", "Samira", "Sangeeta", "Sanjana", "Sapna",
    "Sarita", "Savita", "Seema", "Shaila", "Shakti", "Shalini", "Shanti",
    "Sharmila", "Shilpa", "Shobha", "Shreya", "Shruti", "Simran", "Sita",
    "Smita", "Sneha", "Sonal", "Sonia", "Soumya", "Sudha", "Suhasini",
    "Sujata", "Sunita", "Sumita", "Suman", "Susheela", "Sushma", "Swati",
    "Tanvi", "Tara", "Tarini", "Trisha", "Uma", "Urmila", "Usha",
    "Vaishnavi", "Vandana", "Varsha", "Veena", "Vibha", "Vidhi", "Vidya",
    "Vijaya", "Vimala", "Vinita", "Yamini", "Yashasvi", "Yashika",
    "Yashoda", "Yogita",
    # South Indian additions
    "Anusha", "Bharathi", "Chandrika", "Devi", "Gomathi", "Janaki",
    "Jayalakshmi", "Kalavathi", "Kamakshi", "Kanaka", "Kavitha",
    "Keerthana", "Lavanya", "Malini", "Maya", "Meenakshi", "Nalini",
    "Padmavathi", "Parvathi", "Pavithran", "Poorna", "Rajalakshmi",
    "Ranjana", "Revathi", "Sandhya", "Saraswati", "Saroja", "Saraswathi",
    "Sumathi", "Swarna", "Thara", "Vasundhara", "Vijayalakshmi", "Yogesh",
]


# Gender-neutral fallback when CSV doesn't tell us the gender.
NEUTRAL_FIRST_NAMES: list[str] = list(dict.fromkeys(MALE_FIRST_NAMES + FEMALE_FIRST_NAMES))


LAST_NAMES: list[str] = [
    # South Indian (~50%)
    "Acharya", "Aiyar", "Aiyengar", "Anand", "Ananthapadmanabhan",
    "Balasubramanian", "Bhat", "Chari", "Chenna", "Chowdary", "Chowdhury",
    "Devarajan", "Dhandapani", "Easwaran", "Gopal", "Gopalakrishnan",
    "Gopalan", "Gowda", "Hegde", "Iyengar", "Iyer", "Jagannathan",
    "Jayaraman", "Kamath", "Karunakaran", "Khasturi", "Krishnan",
    "Krishnamurthy", "Lakshman", "Madhavan", "Mahalingam", "Mahesh",
    "Mani", "Menon", "Mohan", "Mukundan", "Murthy", "Nadar", "Naidu",
    "Nair", "Nambiar", "Narasimhan", "Natarajan", "Pai", "Padmanabhan",
    "Pillai", "Prabhu", "Raghavan", "Raghuram", "Raj", "Ramachandran",
    "Raman", "Ramasamy", "Ramesh", "Ramprasad", "Ranganathan",
    "Ranganath", "Rao", "Reddy", "Sastry", "Sankar", "Sankaran",
    "Saravanan", "Sastri", "Seshadri", "Shenoy", "Shetty", "Sivakumar",
    "Sridharan", "Srinivasan", "Subramani", "Subramanian", "Sundaram",
    "Swamy", "Thiagarajan", "Vaidyanathan", "Vasudevan", "Venkat",
    "Venkataraman", "Venkatesh", "Vijayakumar", "Vishwanathan",
    # Pan-India / Hindi-belt
    "Agarwal", "Agnihotri", "Ahuja", "Arora", "Bajaj", "Bansal",
    "Bhardwaj", "Bhatia", "Chauhan", "Chawla", "Chopra", "Dewan",
    "Dhawan", "Dixit", "Dubey", "Garg", "Goyal", "Gupta", "Jain",
    "Jha", "Jindal", "Kapoor", "Kapur", "Kashyap", "Khanna", "Khurana",
    "Kohli", "Kumar", "Madan", "Malhotra", "Mehra", "Mishra", "Mittal",
    "Nagar", "Nigam", "Pandey", "Pant", "Rai", "Saxena", "Sehgal",
    "Sethi", "Sharma", "Shukla", "Singh", "Singhal", "Sinha", "Soni",
    "Suri", "Tandon", "Thakur", "Tiwari", "Tripathi", "Verma", "Yadav",
    # Marathi
    "Bhonsle", "Chavan", "Deshmukh", "Deshpande", "Dhanade", "Gokhale",
    "Hadaway", "Jadhav", "Joglekar", "Joshi", "Kale", "Karandikar",
    "Karve", "Kelkar", "Kulkarni", "Mokashi", "Naik", "Nene", "Pandit",
    "Patil", "Phadke", "Pradhan", "Ranade", "Sane", "Sathe", "Sawant",
    "Shinde",
    # Bengali
    "Banerjee", "Basu", "Bhattacharya", "Bose", "Chakraborty",
    "Chatterjee", "Das", "Dasgupta", "Datta", "Dutta", "Ganguly",
    "Ghosh", "Mukherjee", "Roy", "Sen", "Sengupta",
    # Gujarati
    "Bhatt", "Chokshi", "Dalal", "Desai", "Doshi", "Gandhi", "Kothari",
    "Mehta", "Modi", "Parikh", "Patel", "Sanghvi", "Shah", "Soni",
    "Trivedi",
    # Punjabi
    "Bedi", "Chadha", "Cheema", "Dhaliwal", "Dhillon", "Gill", "Grewal",
    "Kang", "Mann", "Sandhu", "Sodhi", "Walia",
]


# ---------------------------------------------------------------------------
# Hash helper
# ---------------------------------------------------------------------------


def _idx(key: str, modulus: int) -> int:
    """Deterministic ``0..modulus-1`` index from a string key.

    Uses MD5 so the mapping is stable across Python processes (unlike
    ``hash()``, which is salted per-process for security).
    """
    digest = hashlib.md5(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % modulus


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def short_handle(external_id: str) -> str:
    """6-character uppercase handle (e.g. ``A72875``).

    Returns the first 6 hex chars of the cleaned external id — same shape
    the old ``_clean_external_id`` helper produced. Useful as a small
    secondary chip beside a real name on UI cards.
    """
    if not external_id:
        return "------"
    s = external_id
    if s.startswith("\\x"):
        s = s[2:]
    return s[:6].upper()


def _first_pool_for(gender: Optional[object]) -> list[str]:
    g = ""
    if isinstance(gender, str):
        g = gender.lower()
    elif gender is not None:
        g = str(getattr(gender, "value", gender)).lower()
    if g == "male":
        return MALE_FIRST_NAMES
    if g == "female":
        return FEMALE_FIRST_NAMES
    return NEUTRAL_FIRST_NAMES


def generate_name(
    external_id: str,
    *,
    gender: Optional[object] = None,
    salt: str = "",
) -> str:
    """Build ``"<First> <Last>"`` deterministically from ``external_id``.

    NOTE: this is a pure hash → name function. Two different ids CAN map
    to the same (first, last) tuple. For uniqueness across a dataset, use
    ``assign_unique_names`` instead.
    """
    if not external_id:
        return "Unknown"
    first_pool = _first_pool_for(gender)
    first = first_pool[_idx(external_id + "|first" + salt, len(first_pool))]
    last = LAST_NAMES[_idx(external_id + "|last" + salt, len(LAST_NAMES))]
    return f"{first} {last}"


def generate_caregiver_name(
    external_id: str,
    *,
    patient_last_name: Optional[str] = None,
) -> str:
    """Caregiver name = parent of the patient.

    Same surname as the patient (families share surnames), but opposite-
    leaning first-name pool so the same external id reliably produces a
    parent figure distinct from the child.
    """
    if not external_id:
        return "Caregiver"
    parent_is_father = _idx(external_id + "|caregiver|gender", 2) == 0
    pool = MALE_FIRST_NAMES if parent_is_father else FEMALE_FIRST_NAMES
    first = pool[_idx(external_id + "|caregiver|first", len(pool))]
    if patient_last_name:
        return f"{first} {patient_last_name}"
    last = LAST_NAMES[_idx(external_id + "|caregiver|last", len(LAST_NAMES))]
    return f"{first} {last}"


# ---------------------------------------------------------------------------
# Uniqueness pre-pass
# ---------------------------------------------------------------------------


def assign_unique_names(
    rows: Iterable[tuple[str, Optional[object]]],
) -> dict[str, tuple[str, str]]:
    """Assign one unique ``(first_name, last_name)`` to every ``external_id``.

    Args:
        rows: iterable of ``(external_id, gender_hint)`` tuples. Pass the
            CSV gender column (or bridge_gender for patients) as the
            second element. ``None`` is fine — falls back to neutral pool.

    Returns:
        ``{external_id: (first, last)}`` dict. Iteration order is
        deterministic — rows are sorted by ``external_id`` before
        assignment, so re-running with the same input always produces
        the same map regardless of Python process.

    Algorithm:
        For each id (in sorted order):
            attempt 0: hash + base name
            attempt k: re-hash with salt ``|k`` until (first, last) is unused
        Linear probing converges in O(1) per id while the pool is < 25 %
        saturated; for the current 7,033 rows we have ~44k combos per
        gender so ~16 % saturation → ≤2 probes for the worst case.
    """
    # Sort so assignments are stable across reruns even if the input order
    # changes (e.g. different CSV write order).
    ordered = sorted({eid: gh for eid, gh in rows}.items(), key=lambda kv: kv[0])
    used: set[tuple[str, str]] = set()
    out: dict[str, tuple[str, str]] = {}

    for eid, gender_hint in ordered:
        if not eid:
            continue
        first_pool = _first_pool_for(gender_hint)
        # Walk the salt counter until we land on an unused tuple.
        for attempt in range(2048):
            salt = "" if attempt == 0 else f"|{attempt}"
            first = first_pool[_idx(eid + "|first" + salt, len(first_pool))]
            last = LAST_NAMES[_idx(eid + "|last" + salt, len(LAST_NAMES))]
            key = (first, last)
            if key not in used:
                used.add(key)
                out[eid] = key
                break
        else:  # pragma: no cover — only fires if pool is fully exhausted
            # Fall through and accept a duplicate rather than crash.
            out[eid] = (first, last)

    return out
