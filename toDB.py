import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from urllib.request import urlretrieve
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import urllib
import uuid
import json
import requests

import sqlite3

import share.setting as share

def search_product(product_name):
    driver = webdriver.Chrome(share.CHROMEDRIVER)  # 크롬 드라이버 실행

    ### 크롬창 띄우지 않고 크롬드라이버 실행 ###
    # options = webdriver.ChromeOptions()
    # options.add_argument("headless")
    # driver = webdriver.Chrome(options=options)

    driver.get(share.HomeUrl)  # 크롬 드라이버에 url 주소 넣고 실행

    time.sleep(3)  # 페이지가 완전히 로딩되도록 3초동안 기다림
    driver.find_element(By.NAME, "keyword").send_keys(product_name, Keys.ENTER)
    time.sleep(5)

    conn = sqlite3.connect(share.DB_NAME)
    cursor = conn.cursor()  # 커서 생성

    cursor.execute(f"DROP TABLE IF EXISTS {share.DB_NAME}")  # 실행할 때마다 다른 값이 나오지 않도록 테이블을 제거해두기
    # cursor.execute('CREATE TABLE IF NOT EXISTS page_items(ranks INT, name TEXT, price TEXT, link CHAR(255))')
    cursor.execute(f'CREATE TABLE {share.DB_NAME} (NO INT, NAME TEXT, PRICE TEXT, URL CHAR(255))')

    prods = driver.find_elements(By.CLASS_NAME, 'unitItemBox')
    # print(len(prods))
    ranks = 1
    for prod in prods:
        name = prod.find_element(By.CLASS_NAME, "css-12cdo53-defaultStyle-Typography-ellips").text
        price = prod.find_element(By.CLASS_NAME, "priceValue").text
        link = prod.find_element(By.CLASS_NAME, "productTitle").get_attribute('href')

        cursor.execute(f"INSERT INTO {share.DB_NAME} VALUES ({ranks}, {name}, {price}, {link})")
        ranks += 1
        cursor.execute(f"SELECT URL FROM {share.DB_NAME} WHERE NO < 10")
        if ranks == 3:
            #n-1만큼 생성됨
            break

    db_link = cursor.fetchall()
    print(f"현재 테이블의 데이터 수 : {len(db_link)}")

    # 검색한 상품이 없는 경우
    if len(db_link) == 0:
        print("검색된 상품이 없음 / 추후 수정")

    conn.commit()  # 커밋 안 해도 됨
    # conn.close()

    ranks = 0

    cursor.execute("ALTER TABLE ITEM ADD ITEM_IMG_URL CHAR(255)")
    cursor.execute("ALTER TABLE ITEM ADD INFO_IMG_URL CHAR(255)")
    cursor.execute("ALTER TABLE ITEM ADD ALLERGY_INFO TEXT")
    cursor.execute("ALTER TABLE ITEM ADD SEARCH_NO INT")

    for link in db_link:
        ranks += 1
        driver.get(''.join(link))
        time.sleep(3)
        main_link = driver.find_element(By.CLASS_NAME, "thumbSliderWrap").get_attribute('src')

        ### 대표 이미지 저장 ###
        try:
            element = WebDriverWait(driver, 30).until(
                EC.visibility_of_element_located((By.CLASS_NAME, "thumbSlideItem"))
            )
        except:
            print("error")

        main_link = driver.find_element(By.CLASS_NAME, "prodTopImgWrap").find_elements(By.TAG_NAME, 'img')
        main_picture = main_link[0].get_attribute('src')

        ### 영양 정보 이미지 db 저장 ###
        try:
            # 영양정보 이미지 위치로 이동
            driver.execute_script("window.scrollTo(0, 3000)")
            element = WebDriverWait(driver, 30).until(
                EC.visibility_of_element_located((By.CLASS_NAME, "prodLabelImg"))
            )
        except:
            print("error")

        base = driver.find_element(By.CLASS_NAME, "prodDetailArea").find_elements(By.TAG_NAME, 'img')
        src_link = base[-1].get_attribute('src')

        # 상품 메인 이미지, 영양 정보 이미지 src -> db에 저장
        cursor.execute(
            f"UPDATE {share.DB_NAME} SET ITEM_IMG_URL={main_picture}, INFO_IMG_URL={src_link} WHERE NO={ranks}")
        # print(src_link)
        re = naver_clova(src_link)  # 클로바 OCR 실행
        stts_allergy = find_allergy(re)  # 알러지 정보 추출
        string_allergy = ' '.join(stts_allergy)
        string_allergy = string_allergy[:-2]  # 맨 마지막 , 없애기
        cursor.execute(f"UPDATE {share.DB_NAME} SET ALLERGY_INFO={string_allergy} WHERE NO={ranks}")
        # print(string_allergy)

    conn.commit()  # 커밋 후
    # conn.close              # 연결 종료

    # make_tts
    cursor.execute(f"SELECT * FROM {share.DB_NAME}")
    num = 10
    result = cursor.fetchmany(num)

    stts = []
    for re in result:
        product_rank = re[0]
        product_name = re[1]
        product_price = re[2]
        product_allergy = re[-1]
        text = f"{product_rank}번 제품의 이름은 {product_name} 입니다. 가격은 {product_price}원 입니다. 알러지정보는 {product_allergy}입니다."
        stts.append(text)
        # SttAndTts.make_audio(product_rank, text)

    print(stts)
    # conn.commit() # 커밋 안 해도 됨
    conn.close()
    driver.quit()  # 크롬 드라이버 종료
    return 0


def replace_string(all):
    specialchars = "{}[](),/:을"

    for i in specialchars:
        # print(i)
        for a in range(len(all)):
            if (all[a] == i):
                all = all.replace(i, ' ')
    return all


def string_pre(all):
    new_all = []
    for a in range(len(all)):
        # 특수문자 처리
        all[a] = replace_string(all[a])

        # 포함제거
        poham = all[a].find("포함")
        if (poham != -1):
            all[a] = ''

        split_point = 0
        sp_str = all[a].split(" ")
        split_point += len(sp_str)

        for i in range(len(sp_str)):
            new_all.append(sp_str[i])

    new_all = list(filter(None, new_all))

    return new_all


def find_fac(all):
    fac_keyword = ['제품은', '사용한', '제품과', '같은', '제조하고']
    fac_index = []
    for a in range(len(all)):
        for f in fac_keyword:
            if (all[a].find(f) != -1):
                fac_index.append(a)
    fac_index.sort()
    return fac_index


def find_facnum(fac_index):
    f = 0
    point = 0
    for i in range(len(fac_index) - 1):
        if (fac_index[i + 1] - fac_index[i] < 2):
            if (point == 0):
                f = fac_index[i]
            point += 1
            if (point >= 3):
                return f
        else:
            f = 0
            point = 0
    return -1


def find_index(all, keyword):
    index = []
    keys = []
    for a in range(len(all)):
        for k in keyword:
            num = all[a].find(k)
            if (num != -1):
                all[a] = k
                index.append(a)
                break
    index.sort()
    return index


def remove_fac(pre_re, food_index, fac_num):
    if (fac_num == -1):
        new_food_index = []
        new_food_index.append(food_index)
        return new_food_index
    food_index.append(fac_num)
    food_index.sort()
    f = fac_num
    fac = food_index.index(fac_num)
    for i in reversed(food_index[:fac]):
        if (f - i <= 2):
            f = i
        else:
            break

    new_food_index = []
    new_food_index.append(food_index[:food_index.index(f)])

    if (len(food_index) - 1 > food_index.index(fac_num)):
        new_food_index.append(food_index[food_index.index(fac_num):])
    return new_food_index


def stt_string(pre_re, allergy):
    stt = ""
    # print(f"<{name}>의 알러지유발성분 입니다.")
    set_allergy = []
    for a in allergy:
        for i in a:
            set_allergy.append(pre_re[i])
    result = set(set_allergy)
    for a in result:
        stt += a
        stt += ", "
        # print(a,end=' ')
    # print("입니다.")
    return stt


def find_allergy(re):
    keyword = ['메밀', '밀', '대두', '복숭아', '토마토', '우유', '치즈', '굴', '가리비', '전복', '홍합', '땅콩', '계란', '달걀', '고등어', '멸치', '명태',
               '가자미', '명태', '장어', '대구', '참치', '연어', '랍스터', '오징어', '게', '새우', '양고기', '소고기', '돼지고기', '아황산포함식품', '번데기',
               '닭고기', '쇠고기', '오징어', '잣', '오이', '토마토', '당근', '셀러리', '감자', '마늘', '양파', '딸기', '키위', '망고', '바나나', '감귤',
               '사과', '복숭아', '밤', '보리', '옥수수', '쌀', '밀가루', '참깨', '땅콩', '콩', '헤이즐럿', '호두', '카카오', '아모든', '해바라기씨', 'CCD항원',
               '효모', '올리브', '아카시아', '쑥'
                                    '난류', '알류', '견과류', '육류', '갑각류', '조개류', '아황산류']
    ite = 0
    stts = []
    for i in re:
        # print(f"--------------{name_list[ite]}-----------------")
        pre_re = string_pre(i)
        food_index = find_index(pre_re, keyword)
        fac_index = find_fac(pre_re)
        fac_num = find_facnum(fac_index)
        allergy = remove_fac(pre_re, food_index, fac_num)
        stt = stt_string(pre_re, allergy)
        stts.append(stt)
        ite += 1
    return stts


def naver_clova(src_link):
    re = []

    path = "temp/tmp.png"
    urllib.request.urlretrieve(src_link, path)

    files = [('file', open(path, 'rb'))]

    request_json = {'images': [{'format': 'jpg',
                                'name': 'demo'
                                }],
                    'requestId': str(uuid.uuid4()),
                    'version': 'V2',
                    'timestamp': int(round(time.time() * 1000))
                    }

    payload = {'message': json.dumps(request_json).encode('UTF-8')}

    headers = {
        'X-OCR-SECRET': share.secret_key,
    }
    print("응답요청중 ...")
    response = requests.request("POST", share.api_url, headers=headers, data=payload, files=files)
    result = response.json()

    all = []

    for field in result['images'][0]['fields']:
        text = field['inferText']
        all.append(text)
    re.append(all)

    return re



