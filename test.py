import requests

url = "https://www.doctolib.de/authn/patient/realms/doctolib-patient/accounts/check_existence"

payload = {
    "username": "+4915117885291",
    "clientId": "patient-de-client"
}
headers = {
    "host": "www.doctolib.de",
    "connection": "keep-alive",
    "sec-ch-ua-platform": "\"Android\"",
    "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Mobile Safari/537.36",
    "accept": "application/json, text/plain, */*",
    "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Google Chrome\";v=\"138\"",
    "content-type": "application/json",
    "sec-ch-ua-mobile": "?1",
    "origin": "https://www.doctolib.de",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-US,en;q=0.9",
    "cookie": "AUTH_SESSION_ID=1cb3ccfc-73f8-407e-a2a9-b68a40f832c7.keycloak-patients-0-58733; AUTH_SESSION_ID_LEGACY=1cb3ccfc-73f8-407e-a2a9-b68a40f832c7.keycloak-patients-0-58733; __cf_bm=.Tuno1AQxtm3PdMwi7qRIeN2_eNSmwl2RLIdEXdy0WI-1753889926-1.0.1.1-SN3NjK5_BPwK3vc9hMl47TaruPZFcZl7Yxq14MZN0jcXyz8lQ_hB5UUj2MozQ_Zov4fNU53BJUK4AQH9p1vVKVIiy5tlzcjd9OBwCrqU8LP4bM7luvVxWIUcQ2wMf3nQ; _cfuvid=V4q2U1_2OcZil1F4Pa5qgT3CpjehR2ICx4bsM_s9vvw-1753889926803-0.0.1.1-604800000; _dd_s=aid=aaf3dae6-c15a-4455-af55-268a4c40c1f8&rum=0&expire=1753891856024; dl_frcid=322e738d-b038-40f5-bf2e-4b530ac4168f"
}

response = requests.post(url, json=payload, headers=headers)

print(response.status_code)