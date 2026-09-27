"""
Parser module for AGSI Gas Storage Miner.
Supports both live JSON API tree traversal and local HTML snapshot parsing.
"""

import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from bs4 import BeautifulSoup


MONTH_MAP = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12"
}


def to_float(val: Any) -> Optional[float]:
    """Converts string/numeric representation to float or None."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip()
    if not val_str or val_str in ("-", "N/A", "null", "None"):
        return None
    # Remove commas if used as thousands or decimals
    val_str = val_str.replace(" ", "")
    try:
        return float(val_str)
    except ValueError:
        return None


def clean_str(val: Any) -> Optional[str]:
    """Cleans string value, returning None if empty or dash."""
    if val is None:
        return None
    val_str = str(val).strip()
    if not val_str or val_str in ("-", "null", "None"):
        return None
    return val_str


def parse_date_string(date_text: str) -> Optional[str]:
    """
    Parses date text like 'Saturday 26th September, 2026 - Sunday 27th September, 2026'
    or '2026-09-26' into 'YYYY-MM-DD'.
    """
    if not date_text:
        return None
    # ISO date match
    iso_match = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', date_text)
    if iso_match:
        return iso_match.group(1)

    # Worded date match: e.g. 26th September, 2026
    match = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s+(\d{4})', date_text)
    if match:
        day = match.group(1).zfill(2)
        month_name = match.group(2).lower()
        year = match.group(3)
        month = MONTH_MAP.get(month_name)
        if month:
            return f"{year}-{month}-{day}"
    return None


def parse_live_api(api_json: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Parses the 4-tier tree from AGSI live API response.
    Returns structured dictionaries for dimension and facts tables.
    """
    result = {
        "regions": [],
        "countries": [],
        "operators": [],
        "facilities": [],
        "region_storage": [],
        "country_storage": [],
        "operator_storage": [],
        "facility_storage": []
    }

    seen_regions = set()
    seen_countries = set()
    seen_operators = set()
    seen_facilities = set()

    data_nodes = api_json.get("data", [])
    for reg_node in data_nodes:
        raw_reg_code = clean_str(reg_node.get("name")) or "EU"
        reg_code = "EU" if "EU" in raw_reg_code.upper() and "NON" not in raw_reg_code.upper() else "Non-EU"
        reg_name = clean_str(reg_node.get("name")) or reg_code

        if reg_code not in seen_regions:
            seen_regions.add(reg_code)
            result["regions"].append({
                "code": reg_code,
                "name": reg_name
            })

        gas_day = clean_str(reg_node.get("gasDayEnd")) or clean_str(reg_node.get("gasDayStart"))
        gas_day_start = clean_str(reg_node.get("gasDayStart"))
        gas_day_end = clean_str(reg_node.get("gasDayEnd"))

        result["region_storage"].append({
            "region_code": reg_code,
            "gas_day": gas_day,
            "gas_day_start": gas_day_start,
            "gas_day_end": gas_day_end,
            "status": clean_str(reg_node.get("status")),
            "gas_in_storage": to_float(reg_node.get("gasInStorage")),
            "full_percentage": to_float(reg_node.get("full")),
            "trend": to_float(reg_node.get("trend")),
            "injection": to_float(reg_node.get("injection")),
            "withdrawal": to_float(reg_node.get("withdrawal")),
            "net_withdrawal": to_float(reg_node.get("netWithdrawal")),
            "working_gas_volume": to_float(reg_node.get("workingGasVolume")),
            "injection_capacity": to_float(reg_node.get("injectionCapacity")),
            "withdrawal_capacity": to_float(reg_node.get("withdrawalCapacity")),
            "covered_capacity": to_float(reg_node.get("coveredCapacity")),
            "updated_at_source": clean_str(reg_node.get("updatedAt"))
        })

        # Country nodes
        for ctry_node in reg_node.get("children", []):
            ctry_code = clean_str(ctry_node.get("code")) or clean_str(ctry_node.get("url")) or clean_str(ctry_node.get("name"))
            ctry_name = clean_str(ctry_node.get("name"))

            if ctry_code not in seen_countries:
                seen_countries.add(ctry_code)
                result["countries"].append({
                    "code": ctry_code,
                    "name": ctry_name,
                    "region_code": reg_code
                })

            c_gas_day = clean_str(ctry_node.get("gasDayEnd")) or gas_day
            result["country_storage"].append({
                "country_code": ctry_code,
                "gas_day": c_gas_day,
                "gas_day_start": clean_str(ctry_node.get("gasDayStart")) or gas_day_start,
                "gas_day_end": clean_str(ctry_node.get("gasDayEnd")) or gas_day_end,
                "status": clean_str(ctry_node.get("status")),
                "gas_in_storage": to_float(ctry_node.get("gasInStorage")),
                "full_percentage": to_float(ctry_node.get("full")),
                "trend": to_float(ctry_node.get("trend")),
                "injection": to_float(ctry_node.get("injection")),
                "withdrawal": to_float(ctry_node.get("withdrawal")),
                "net_withdrawal": to_float(ctry_node.get("netWithdrawal")),
                "working_gas_volume": to_float(ctry_node.get("workingGasVolume")),
                "injection_capacity": to_float(ctry_node.get("injectionCapacity")),
                "withdrawal_capacity": to_float(ctry_node.get("withdrawalCapacity")),
                "contracted_capacity": to_float(ctry_node.get("contractedCapacity")),
                "available_capacity": to_float(ctry_node.get("availableCapacity")),
                "consumption": to_float(ctry_node.get("consumption")),
                "consumption_full": to_float(ctry_node.get("consumptionFull")),
                "covered_capacity": to_float(ctry_node.get("coveredCapacity")),
                "updated_at_source": clean_str(ctry_node.get("updatedAt"))
            })

            # Operator nodes
            for comp_node in ctry_node.get("children", []):
                op_code = clean_str(comp_node.get("code")) or clean_str(comp_node.get("url")) or clean_str(comp_node.get("name"))
                op_name = clean_str(comp_node.get("name"))

                if op_code not in seen_operators:
                    seen_operators.add(op_code)
                    result["operators"].append({
                        "code": op_code,
                        "name": op_name,
                        "country_code": ctry_code,
                        "publication_link": clean_str(comp_node.get("publication_link")),
                        "transparency_template": clean_str(comp_node.get("transparency_template"))
                    })

                op_gas_day = clean_str(comp_node.get("gasDayEnd")) or c_gas_day
                result["operator_storage"].append({
                    "operator_code": op_code,
                    "gas_day": op_gas_day,
                    "gas_day_start": clean_str(comp_node.get("gasDayStart")) or gas_day_start,
                    "gas_day_end": clean_str(comp_node.get("gasDayEnd")) or gas_day_end,
                    "status": clean_str(comp_node.get("status")),
                    "gas_in_storage": to_float(comp_node.get("gasInStorage")),
                    "full_percentage": to_float(comp_node.get("full")),
                    "trend": to_float(comp_node.get("trend")),
                    "injection": to_float(comp_node.get("injection")),
                    "withdrawal": to_float(comp_node.get("withdrawal")),
                    "net_withdrawal": to_float(comp_node.get("netWithdrawal")),
                    "working_gas_volume": to_float(comp_node.get("workingGasVolume")),
                    "injection_capacity": to_float(comp_node.get("injectionCapacity")),
                    "withdrawal_capacity": to_float(comp_node.get("withdrawalCapacity")),
                    "contracted_capacity": to_float(comp_node.get("contractedCapacity")),
                    "available_capacity": to_float(comp_node.get("availableCapacity")),
                    "covered_capacity": to_float(comp_node.get("coveredCapacity")),
                    "updated_at_source": clean_str(comp_node.get("updatedAt"))
                })

                # Facility nodes
                for fac_node in comp_node.get("children", []):
                    fac_code = clean_str(fac_node.get("code")) or clean_str(fac_node.get("url")) or clean_str(fac_node.get("name"))
                    fac_name = clean_str(fac_node.get("name"))

                    if fac_code not in seen_facilities:
                        seen_facilities.add(fac_code)
                        result["facilities"].append({
                            "code": fac_code,
                            "name": fac_name,
                            "operator_code": op_code,
                            "country_code": ctry_code,
                            "facility_type": clean_str(fac_node.get("type")),
                            "latitude": to_float(fac_node.get("latitude")),
                            "longitude": to_float(fac_node.get("longitude"))
                        })

                    fac_gas_day = clean_str(fac_node.get("gasDayEnd")) or op_gas_day
                    result["facility_storage"].append({
                        "facility_code": fac_code,
                        "gas_day": fac_gas_day,
                        "gas_day_start": clean_str(fac_node.get("gasDayStart")) or gas_day_start,
                        "gas_day_end": clean_str(fac_node.get("gasDayEnd")) or gas_day_end,
                        "status": clean_str(fac_node.get("status")),
                        "gas_in_storage": to_float(fac_node.get("gasInStorage")),
                        "full_percentage": to_float(fac_node.get("full")),
                        "trend": to_float(fac_node.get("trend")),
                        "injection": to_float(fac_node.get("injection")),
                        "withdrawal": to_float(fac_node.get("withdrawal")),
                        "net_withdrawal": to_float(fac_node.get("netWithdrawal")),
                        "working_gas_volume": to_float(fac_node.get("workingGasVolume")),
                        "injection_capacity": to_float(fac_node.get("injectionCapacity")),
                        "withdrawal_capacity": to_float(fac_node.get("withdrawalCapacity")),
                        "contracted_capacity": to_float(fac_node.get("contractedCapacity")),
                        "available_capacity": to_float(fac_node.get("availableCapacity")),
                        "updated_at_source": clean_str(fac_node.get("updatedAt"))
                    })

    return result


def parse_html_file(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Parses a local AGSI HTML file snapshot (e.g. Gas Infrastructure Europe - AGSI.html).
    Extracts the Tabulator DOM tree and maps to explicit dimension and metric tables.
    """
    result = {
        "regions": [],
        "countries": [],
        "operators": [],
        "facilities": [],
        "region_storage": [],
        "country_storage": [],
        "operator_storage": [],
        "facility_storage": []
    }

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f, "html.parser")

    # Extract gas day from header or date span
    date_span = soup.find("span", id="date")
    gas_day = parse_date_string(date_span.get_text()) if date_span else None
    if not gas_day:
        # Fallback check any date text
        for el in soup.find_all(["span", "p", "div"]):
            parsed = parse_date_string(el.get_text())
            if parsed:
                gas_day = parsed
                break
    if not gas_day:
        gas_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    seen_regions = set()
    seen_countries = set()
    seen_operators = set()
    seen_facilities = set()

    current_region = None
    current_country = None
    current_operator = None

    rows = soup.find_all("div", class_="tabulator-row")
    for r in rows:
        # Determine tree level
        lvl = 0
        for c in r.get("class", []):
            if c.startswith("tabulator-tree-level-"):
                lvl = int(c.split("-")[-1])
                break

        def get_field(field_name: str) -> Optional[str]:
            el = r.find("div", attrs={"tabulator-field": field_name})
            return el.get_text(strip=True) if el else None

        name = get_field("name")
        if not name:
            continue

        # Extract links and potential codes / coords
        links = [a.get("href") for a in r.find_all("a") if a.get("href")]
        code = None
        extracted_country = None
        extracted_operator = None
        lat, lng = None, None

        for link in links:
            if "/data-overview/" in link and "/graphs/" not in link:
                parts = link.split("/data-overview/")[-1].split("/")
                if len(parts) >= 1 and parts[0]:
                    code = parts[0]
                if len(parts) >= 2 and parts[1]:
                    extracted_country = parts[1]
                if len(parts) >= 3 and parts[2]:
                    extracted_operator = parts[2]
            if "map?" in link:
                m_lat = re.search(r'lat=([-\d.]+)', link)
                m_lng = re.search(r'lng=([-\d.]+)', link)
                if m_lat and m_lng:
                    lat, lng = float(m_lat.group(1)), float(m_lng.group(1))

        status = get_field("status")
        gis = to_float(get_field("gasInStorage"))
        full = to_float(get_field("full"))
        trend = to_float(get_field("trend"))
        consumption = to_float(get_field("consumption"))
        consumption_full = to_float(get_field("consumptionFull"))
        injection = to_float(get_field("injection"))
        withdrawal = to_float(get_field("withdrawal"))
        wgv = to_float(get_field("workingGasVolume"))
        inj_cap = to_float(get_field("injectionCapacity"))
        with_cap = to_float(get_field("withdrawalCapacity"))
        con_cap = to_float(get_field("contractedCapacity"))
        av_cap = to_float(get_field("availableCapacity"))
        cov_cap = to_float(get_field("coveredCapacity"))
        net_with = round(withdrawal - injection, 2) if (withdrawal is not None and injection is not None) else None

        # Level 0: Region (EU, Non-EU)
        if lvl == 0:
            reg_code = "Non-EU" if "NON" in name.upper() else "EU"
            current_region = reg_code
            if reg_code not in seen_regions:
                seen_regions.add(reg_code)
                result["regions"].append({
                    "code": reg_code,
                    "name": name
                })
            result["region_storage"].append({
                "region_code": reg_code,
                "gas_day": gas_day,
                "gas_day_start": None,
                "gas_day_end": None,
                "status": status,
                "gas_in_storage": gis,
                "full_percentage": full,
                "trend": trend,
                "injection": injection,
                "withdrawal": withdrawal,
                "net_withdrawal": net_with,
                "working_gas_volume": wgv,
                "injection_capacity": inj_cap,
                "withdrawal_capacity": with_cap,
                "covered_capacity": cov_cap,
                "updated_at_source": None
            })

        # Level 1: Country
        elif lvl == 1:
            ctry_code = code or name[:3].upper()
            current_country = ctry_code
            reg_code = current_region or "EU"
            if ctry_code not in seen_countries:
                seen_countries.add(ctry_code)
                result["countries"].append({
                    "code": ctry_code,
                    "name": name,
                    "region_code": reg_code
                })
            result["country_storage"].append({
                "country_code": ctry_code,
                "gas_day": gas_day,
                "gas_day_start": None,
                "gas_day_end": None,
                "status": status,
                "gas_in_storage": gis,
                "full_percentage": full,
                "trend": trend,
                "injection": injection,
                "withdrawal": withdrawal,
                "net_withdrawal": net_with,
                "working_gas_volume": wgv,
                "injection_capacity": inj_cap,
                "withdrawal_capacity": with_cap,
                "contracted_capacity": con_cap,
                "available_capacity": av_cap,
                "consumption": consumption,
                "consumption_full": consumption_full,
                "covered_capacity": cov_cap,
                "updated_at_source": None
            })

        # Level 2: Operator
        elif lvl == 2:
            op_code = code or re.sub(r'[^a-zA-Z0-9]', '', name)[:32]
            current_operator = op_code
            ctry_code = extracted_country or current_country or "UNKNOWN"
            if op_code not in seen_operators:
                seen_operators.add(op_code)
                result["operators"].append({
                    "code": op_code,
                    "name": name,
                    "country_code": ctry_code,
                    "publication_link": None,
                    "transparency_template": None
                })
            result["operator_storage"].append({
                "operator_code": op_code,
                "gas_day": gas_day,
                "gas_day_start": None,
                "gas_day_end": None,
                "status": status,
                "gas_in_storage": gis,
                "full_percentage": full,
                "trend": trend,
                "injection": injection,
                "withdrawal": withdrawal,
                "net_withdrawal": net_with,
                "working_gas_volume": wgv,
                "injection_capacity": inj_cap,
                "withdrawal_capacity": with_cap,
                "contracted_capacity": con_cap,
                "available_capacity": av_cap,
                "covered_capacity": cov_cap,
                "updated_at_source": None
            })

        # Level 3: Facility
        elif lvl == 3:
            fac_code = code or re.sub(r'[^a-zA-Z0-9]', '', name)[:32]
            op_code = extracted_operator or current_operator or "UNKNOWN"
            ctry_code = extracted_country or current_country or "UNKNOWN"
            if fac_code not in seen_facilities:
                seen_facilities.add(fac_code)
                result["facilities"].append({
                    "code": fac_code,
                    "name": name,
                    "operator_code": op_code,
                    "country_code": ctry_code,
                    "facility_type": None,
                    "latitude": lat,
                    "longitude": lng
                })
            result["facility_storage"].append({
                "facility_code": fac_code,
                "gas_day": gas_day,
                "gas_day_start": None,
                "gas_day_end": None,
                "status": status,
                "gas_in_storage": gis,
                "full_percentage": full,
                "trend": trend,
                "injection": injection,
                "withdrawal": withdrawal,
                "net_withdrawal": net_with,
                "working_gas_volume": wgv,
                "injection_capacity": inj_cap,
                "withdrawal_capacity": with_cap,
                "contracted_capacity": con_cap,
                "available_capacity": av_cap,
                "updated_at_source": None
            })

    return result
