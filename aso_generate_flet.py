import flet as ft
from flet import Colors, Icons, FontWeight, TextAlign, ThemeMode, ScrollMode, KeyboardType
import os
import pandas as pd
from openai import OpenAI
import json
import re
import itertools
from collections import Counter
import logging
import asyncio
from typing import Optional, List, Dict, Any
import tempfile
import base64
import datetime
import io

# API anahtarı direkt kod içinde
open_ai_key = 
# OpenAI client oluştur
client = OpenAI(api_key=open_ai_key)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='app.log'
)

class color():
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    MAGENTA = "\033[35m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    RESET = "\033[0m"

# Mevcut Df_Get sınıfını aynı şekilde kopyalayıp paste ediyorum
class Df_Get():
    def merged_noduplicate_df(klasor_yolu):
        """
        Klasördeki tüm .csv dosyalarını birleştirir,
        Keyword, Volume ve Difficulty sütunlarına göre tekrarlı satırları kaldırır,
        tüm sütunları saklayarak bir DataFrame döndürür.
        Title sütunu CSV dosya isimlerinden oluşturulur.
        """
        print("DEBUG: merged_noduplicate_df() başlatıldı. Klasör:", klasor_yolu)
        try:
            csv_dosyalar = [f for f in os.listdir(klasor_yolu) if f.endswith('.csv')]
            print("DEBUG: Bulunan CSV dosyaları:", csv_dosyalar)
            if not csv_dosyalar:
                raise ValueError("Klasörde hiç .csv dosyası bulunamadı!")
            
            dataframes = []
            for dosya in csv_dosyalar:
                df_temp = pd.read_csv(os.path.join(klasor_yolu, dosya))
                print(f"DEBUG: {dosya} okundu, şekli: {df_temp.shape}")
                
                # Dosya adından Title oluştur
                # "trending-keywords-US-Business.csv" -> "Business"
                # "trending-keywords-US-Food & Drink.csv" -> "Food & Drink"
                dosya_adi = dosya.replace('.csv', '')
                parts = dosya_adi.split('-')
                if len(parts) >= 4 and parts[0] == 'trending' and parts[1] == 'keywords':
                    # US kısmından sonraki tüm kısımları birleştir
                    title = '-'.join(parts[3:])  # US kısmından sonrasını al
                else:
                    # Fallback: dosya adının son kısmını al
                    title = dosya_adi.split('-')[-1] if '-' in dosya_adi else dosya_adi
                
                # Title sütununu DataFrame'e ekle
                df_temp['Title'] = title
                print(f"DEBUG: {dosya} için Title: {title}")
                
                dataframes.append(df_temp)

            # Bütün CSV'ler birleştiriliyor
            birlesik_df = pd.concat(dataframes, ignore_index=True)
            
            # Title sütununu en başa taşı
            cols = birlesik_df.columns.tolist()
            if 'Title' in cols:
                cols.remove('Title')
                cols.insert(0, 'Title')
                birlesik_df = birlesik_df[cols]
            
            # Öncelikle, Difficulty sütununa göre azalan sırayla sıralıyoruz
            birlesik_df.sort_values(by="Difficulty", ascending=False, inplace=True)

            # Sadece Keyword sütunundaki tekrarları kaldırıp,
            # en yüksek Difficulty değerine sahip satırı tutuyoruz
            birlesik_df.drop_duplicates(subset=["Keyword"], keep="first", ignore_index=True, inplace=True)

            print("DEBUG: Birleştirilmiş DataFrame şekli:", birlesik_df.shape)
            print("DEBUG: Sütunlar:", birlesik_df.columns.tolist())
            return birlesik_df

        except Exception as e:
            raise ValueError(f"CSV birleştirme hatası: {e}")
        
    def kvd_df(df,limit):
        df_filtered = df[(df["Volume"] >= 20) & (df["Difficulty"] <= limit)]
        df_filtered.loc[:, "Volume"] = pd.to_numeric(df_filtered["Volume"], errors="coerce")
        df_filtered = df_filtered.dropna(subset=["Volume"])  
        df_filtered["Volume"] = df_filtered["Volume"].astype(int)
        df_filtered.sort_values(by="Volume", ascending=False, inplace=True)
        
        # Title sütunu varsa koru, yoksa sadece temel sütunları al
        if 'Title' in df_filtered.columns:
            df_result = df_filtered[["Title", "Keyword", "Volume", "Difficulty"]].dropna()
        else:
            df_result = df_filtered[["Keyword", "Volume", "Difficulty"]].dropna()
            
        print("DEBUG: Filtrelenmiş ve sıralanmış KVD CSV:\n", df_result)
        return df_result

    def kelime_frekans_df(df, openai_api_key):
        print("DEBUG: kelime_frekans_df() başlatıldı.")
        kelimeler = " ".join(df["Keyword"].astype(str)).split()
        print("DEBUG: Birleştirilmiş kelimeler:", kelimeler)
        kelime_sayaci = Counter(kelimeler)
        df_kf = pd.DataFrame(kelime_sayaci.items(), columns=["Kelime", "Frekans"]).sort_values(by="Frekans", ascending=False)
        
        # Eğer orijinal df'de Title sütunu varsa, frekans tablosuna da ekle
        if 'Title' in df.columns and not df.empty:
            # En yaygın Title'ı kullan (basit yaklaşım)
            most_common_title = df['Title'].mode().iloc[0] if len(df['Title'].mode()) > 0 else "Frequency"
            df_kf['Title'] = most_common_title
            # Title sütununu en başa taşı
            cols = df_kf.columns.tolist()
            cols.remove('Title')
            cols.insert(0, 'Title')
            df_kf = df_kf[cols]
        
        print("DEBUG: Frekans DataFrame'i:\n", df_kf)
        return df_kf

    def without_branded_kf_df_get(df_kf, openai_api_key):
        """
        Branded kelimeleri ve yasaklı kelimeleri DataFrame'den filtreler.
        """
        try:
            word_list = df_kf['Kelime'].tolist()
            
            yasakli_kelimeler = [
                "free", "new", "best", "top", "iphone", "ipad", "android", "google", "store", 
                "download", "downloads", "for", "apple", "with", "yours", "a", "about", "above", "after", "again", "against", "all", 
                "am", "an", "and", "any", "app", "are", "aren't", "as", "at", "be", "because", "been", "before", "being", "below", 
                "between", "both", "but", "by", "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does", "doesn't", 
                "doing", "don't", "down", "during", "each", "few", "from", "further", "had", "hadn't", "has", "hasn't", "have", 
                "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here", "here's", "hers", "herself", "him", "himself", 
                "his", "how", "how's", "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", 
                "itself", "let's", "me", "more", "most", "mustn't", "my", "myself", "no", "nor", "not", "of", "off", "on", "once", 
                "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she", "she'd", 
                "she'll", "she's", "should", "shouldn't", "so", "some", "such", "than", "that", "that's", "the", "their", "theirs", 
                "them", "themselves", "then", "there", "there's", "these", "they", "they'd", "they'll", "they're", "they've", "this", 
                "those", "through", "to", "too", "under", "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", 
                "we've", "were", "weren't", "what", "what's", "when", "when's", "where", "where's", "which", "while", "who", "who's", 
                "whom", "why", "why's", "won't", "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours", 
                "yourself", "yourselves"]
            
            system_prompt = """
You are an expert in identifying branded words and proper nouns. Your task is to determine if the given words are branded words or proper nouns (like "Williams", "Sherwin", etc.).
You need to identify and return only the words that are branded or proper nouns from the provided list.

Here is the task in detail:
1. Review the following list of words.
2. Identify the branded words and proper nouns.
3. Return the list of identified branded words and proper nouns in the following format:

Example:
- Input: ["Apple", "car", "Sherwin", "painting"]
- Output: ["Apple", "Sherwin"]

*Important*: 
- Only include the branded words and proper nouns in the returned list, and avoid any other words."""
            
            user_prompt = f"""
            Here is the list of words:
            {word_list}

            Return the list of branded words and proper nouns in the following format:
            ["word1", "word2", "word3"]
            """
            
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                max_tokens=150
            )
            
            answer = response.choices[0].message.content.strip()
            print(f'{color.RED}DEBUG:BRANDED API yanıtı:{color.RESET} {answer}')
            
            try:
                branded_data = json.loads(answer)
                print("DEBUG: JSON başarıyla ayrıştırıldı:", branded_data)
                branded_words = [str(item).lower() for item in branded_data] if isinstance(branded_data, list) else []
            except json.JSONDecodeError:
                print("DEBUG: JSON ayrıştırma hatası, manuel işleme yapılıyor")
                cleaned = answer.replace("[", "").replace("]", "").replace('"', '').strip()
                branded_words = [w.strip().lower() for w in cleaned.split(",") if w.strip()]
                print("DEBUG: Manuel temizlenmiş veri:", branded_words)

            # Kelime filtresi oluştur ve mask ile filtreleme yap
            mask = ~(df_kf['Kelime'].str.lower().isin(branded_words) | 
                    df_kf['Kelime'].str.lower().isin(yasakli_kelimeler))
            
            # Filtrelenmiş DataFrame'i oluştur
            filtered_df = df_kf[mask].copy()
            
            # Title sütunu varsa koru
            if 'Title' in df_kf.columns:
                # Title sütununu en başta tut
                cols = filtered_df.columns.tolist()
                if 'Title' in cols and cols[0] != 'Title':
                    cols.remove('Title')
                    cols.insert(0, 'Title')
                    filtered_df = filtered_df[cols]
            
            print(f"DEBUG: Filtrelenmiş kelime sayısı: {len(filtered_df)}")
            return filtered_df
            
        except Exception as e:
            print(f"HATA: {str(e)}")
            return pd.DataFrame(columns=['Kelime', 'Frekans'])

    def aggregate_frequencies(df):
        """
        Aynı kelimeleri birleştirerek frekans değerlerini toplar.
        Title sütunu varsa korur.
        """
        try:
            if df is None or df.empty:
                print("\033[31mHATA: Boş veya geçersiz DataFrame\033[0m")
                return pd.DataFrame(columns=['Kelime', 'Frekans'])

            # Title sütunu varsa koru
            if 'Title' in df.columns:
                # Önce Title'ı al
                title_value = df['Title'].iloc[0] if not df.empty else "Aggregated"
                # Kelime bazında grupla
                aggregated_df = df.groupby("Kelime", as_index=False)["Frekans"].sum()
                # Title'ı geri ekle
                aggregated_df['Title'] = title_value
                # Title'ı en başa taşı
                cols = ['Title', 'Kelime', 'Frekans']
                aggregated_df = aggregated_df[cols]
            else:
                aggregated_df = df.groupby("Kelime", as_index=False)["Frekans"].sum()
            
            print("\033[32mDEBUG: Frekanslar birleştirildi.\033[0m")
            return aggregated_df
        
        except Exception as e:
            print(f"\033[31mHATA: Genel hata: {str(e)}\033[0m")
            return pd.DataFrame(columns=['Kelime', 'Frekans'])
        
    def without_suffixes_df_get(kf_df, selected_country,openai_api_key):
        """
        Kelimelerin çoğul eklerini kaldırır ve tekil formlarını döndürür.
        """
        try:
            if kf_df is None or kf_df.empty:
                print("\033[31mHATA: Boş veya geçersiz DataFrame\033[0m")
                return pd.DataFrame(columns=['Kelime', 'Frekans'])
            
            keyword_list = kf_df['Kelime'].dropna().tolist()
            if not keyword_list:
                print("\033[33mUYARI: Kelime listesi boş\033[0m")
                return pd.DataFrame(columns=['Kelime', 'Frekans'])

            print(f"{color.CYAN}DEBUG: SUFFİXES COUNTRY:{selected_country}{color.RESET}")
            
            system_prompt = f"""
You are an expert in language processing. Your task is:
1. Given a Python list of keywords in the language relevant to the market of {selected_country},
2. Remove only the plural suffixes from each word to return the singular/base form. For example, if the keywords are in English (as in the {selected_country} market when applicable), remove plural suffixes such as -s, -es, and -ies. If the keywords are in another language, apply the appropriate plural suffix removal rules according to the language conventions of {selected_country}.
3. If a word does not end with any of these plural suffixes, leave it unchanged.
4. Provide the final answer strictly as a Python list of strings.

Example:
- Input: ["cats", "boxes", "stories", "apple"]
- Output: ["cat", "box", "story", "apple"]

**WARNING**: Only remove plural suffixes. Do not remove any other suffix or modify the word in any other way.
"""

            user_prompt = f"""
            Here is the list of words:
            {keyword_list}

            Return the processed list in JSON list format. For example:
            ["word1","word2","word3"]
            """

            try:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0,
                    timeout=60
                )

                answer = response.choices[0].message.content.strip()
                print(f"\033[34mDEBUG: Suffixes API yanıtı: {answer}\033[0m")

                # Yanıtın başında ve sonunda üçlü tırnak içeren kod bloğu olup olmadığını kontrol et ve temizle
                if answer.startswith("```json") or answer.startswith("```python"):
                    answer = answer.split("```")[1]
                    answer = answer.replace("json", "").replace("python", "").strip()
                    answer = answer.split("```")[0]

                try:
                    base_form_list = json.loads(answer)

                    if not isinstance(base_form_list, list) or not base_form_list:
                        raise ValueError("API yanıtı geçerli bir liste değil veya boş.")

                    if len(base_form_list) != len(keyword_list):
                        print(f"\033[33mUYARI: API yanıt uzunluğu ({len(base_form_list)}) keyword listesi uzunluğu ({len(keyword_list)}) ile eşleşmiyor. Orijinal liste kullanılacak.\033[0m")
                        base_form_list = keyword_list

                    kf_df['Frekans'] = kf_df['Frekans'].fillna(0)

                    result_df = pd.DataFrame({
                        'Kelime': base_form_list,
                        'Frekans': kf_df['Frekans']
                    })
                    
                    # Title sütunu varsa koru
                    if 'Title' in kf_df.columns:
                        title_value = kf_df['Title'].iloc[0] if not kf_df.empty else "Suffixes"
                        result_df['Title'] = title_value
                    
                    result_df = Df_Get.aggregate_frequencies(result_df)
                    result_df = result_df.sort_values(by='Frekans', ascending=False)

                    print(f"\033[32mDEBUG: İşlenmiş kelime sayısı: {len(result_df)}\033[0m")
                    return pd.DataFrame(result_df)

                except json.JSONDecodeError as e:
                    print(f"\033[31mHATA: JSON ayrıştırma hatası: {str(e)}\033[0m")
                    return kf_df

            except Exception as e:
                print(f"\033[31mHATA: API çağrısı veya işleme hatası: {str(e)}\033[0m")
                return kf_df

        except Exception as e:
            print(f"\033[31mHATA: Genel hata: {str(e)}\033[0m")
            return pd.DataFrame(columns=['Kelime', 'Frekans'])

    def gpt_Title_Subtitle_df_get(df, app_name, selected_country, openai_api_key, retry_count=0, max_retries=3):
        print(f"DEBUG: gpt_Title_Subtitle_df() başlatıldı. retry_count={retry_count}")
        print(f"{color.YELLOW}gpt_Title_Subtitle_df_get için kullanılan df:\n{df}{color.RESET}")
        df_sorted = df.sort_values(by='Frekans', ascending=False)
        top_keywords = df_sorted['Kelime'].tolist()
        print("DEBUG: En sık kullanılan kelimeler:", top_keywords)
        
        prompt_system = f'''
You are an experienced ASO (App Store Optimization) expert. Your task is to generate optimized Title and Subtitle for an app based on the provided keyword data, taking into account the market characteristics of the selected country: **{selected_country}**.

I will provide you with a list of keywords sorted by frequency. Based on this information, your task is to generate the most optimized Title and Subtitle for an app's App Store page for the {selected_country} market. Here are the detailed rules:

1. **Title**:
- Must include the app name: **{app_name}**
- The title must be no longer than **30 characters** and no shorter than **25 characters**.
- Use the most frequent keywords first, prioritizing those at the beginning of the provided list.
- Ensure that the titles are unique and not repetitive; each generated title should use a different combination of keywords.
- **Do not include any of the following words like: "and", "or", "your", "my", "with", etc.**

2. **Subtitle**:
- It must not exceed **30 characters** and no shorter than **25 characters**.
- Do not repeat any keywords used in the Title.
- Use the most frequent keywords first, prioritizing those at the beginning of the provided list.
- Ensure that the subtitles are unique and distinct from each other.
- **Do not include any of the following words like: "and", "or", "your", "my", "with".**

3. **Important**:
- Focus on using keywords from the beginning of the provided list, where the frequency values are higher.
- Make sure the Title and Subtitle align with these rules to maximize the app's visibility and effectiveness in the App Store.
- **Do not include any of the following words like: "and", "or", "your", "my", "with".**
- *Only generate 5 title and 5 subtitle*
'''
        
        prompt_user = f'''
Here are the most frequent keywords:
{','.join(top_keywords)}
- **The title and subtitle must be no longer than 30 characters and no shorter than 25 characters.**
- **Do not include any of the following words like: "and", "or", "your", "my", "with".**
- *Only generate 5 title and 5 subtitle*

**Provide the output strictly in the following JSON format:**
json
{{
"data": [
    {{"Title": "Generated Title", "Subtitle": "Generated Subtitle"}},
    {{"Title": "Generated Title", "Subtitle": "Generated Subtitle"}},
    {{"Title": "Generated Title", "Subtitle": "Generated Subtitle"}},
    {{"Title": "Generated Title", "Subtitle": "Generated Subtitle"}},
    {{"Title": "Generated Title", "Subtitle": "Generated Subtitle"}}
]
}}
'''
        
        print('\033[31m\033[44mDEBUG: OpenAI isteği hazırlanıyor\033[0m')
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": prompt_system},
                    {"role": "user", "content": prompt_user}
                ],
                temperature=0.7,
                max_tokens=539,
            )
            text_output = response.choices[0].message.content
            
            def parse_openai_json(text_output):
                match = re.search(r'```json\s*(\{.*?\})\s*```', text_output, re.DOTALL)
                
                if match:
                    json_text = match.group(1)
                    print("DEBUG: JSON formatı bulundu.")
                else:
                    json_text = text_output
                    print("DEBUG: Tüm metin JSON olarak kullanılacak.")
                
                json_text = json_text.strip()
                json_text = json_text.replace(""", "\"").replace(""", "\"")
                json_text = json_text.encode("utf-8", "ignore").decode("utf-8", "ignore")

                output_data = json.loads(json_text)
                return output_data

            try:
                parsed = parse_openai_json(text_output)
                print(parsed)
            except json.JSONDecodeError as e:
                print("JSON hatası yakalandı:", e)

            title_stitle_df = pd.DataFrame(parse_openai_json(text_output)["data"], columns=["Title", "Subtitle"])
            print("DEBUG: API yanıtından oluşturulan DataFrame:\n", title_stitle_df)

            unused_keywords_list = []  
            title_len_list = []
            subtitle_len_list = []
            toplam_keywords_lenght_list = []

            for index, row in title_stitle_df.iterrows():
                top_keywords_for_for = set()
                top_keywords_for_for = top_keywords
                title_words = set(row["Title"].split())  
                subtitle_words = set(row["Subtitle"].split())  

                title_len_list.append(len(row["Title"]))
                subtitle_len_list.append(len(row["Subtitle"]))

                used_keywords = title_words.union(subtitle_words)
                used_keywords = set(item.lower() for item in used_keywords)
                print("\033[32mDEBUG: Used_Keyword Çıktısı: \033[0m", used_keywords)

                unused_keywords = [kw for kw in top_keywords_for_for if kw.lower() not in used_keywords]
                print("\033[33mUnused_Keyword:\033[0m", unused_keywords)

                result_str = ""
                for keyword in unused_keywords:
                    candidate = keyword if result_str == "" else result_str + "," + keyword
                    try:
                        if len(candidate) <= 100:
                            result_str = candidate
                        else:
                            toplam_keywords_lenght_list.append(len(result_str))
                            break
                    except ValueError as e:
                        if "Length of values" in str(e) and "does not match length of index" in str(e):
                            print("DEBUG: unused_keywords_list uzunluğu DataFrame indeks uzunluğu ile uyuşmuyor!")
                            toplam_keywords_lenght_list.append(len(result_str))
                        else:
                            raise

                print("\033[34mresult_str:\n\033[0m", result_str)
                unused_keywords_list.append(result_str)

            title_stitle_df["Keywords"] = unused_keywords_list
            title_stitle_df["Keywords_Lenght"] = toplam_keywords_lenght_list
            title_stitle_df["Title_Lenght"] = title_len_list
            title_stitle_df["Subtitle_Lenght"] = subtitle_len_list

            print("DEBUG: Son DataFrame (gpt_Title_Subtitle_df()):\n", title_stitle_df)
            return title_stitle_df

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            print("DEBUG: gpt_Title_Subtitle_df() hatası:", e)
            return pd.DataFrame(columns=["Title", "Subtitle"])
        
    def find_matching_keywords(title_subtitle_df, merged_df):
        print(f"\033[34mDEBUG: find_matching_keywords() başladı.\033[0m")
        results = []
        matched_keywords_result = []

        for gpt_idx, gpt_row in title_subtitle_df.iterrows():
            title_words = set(str(gpt_row['Title']).lower().split()) if pd.notna(gpt_row['Title']) else set()
            subtitle_words = set(str(gpt_row['Subtitle']).lower().split()) if pd.notna(gpt_row['Subtitle']) else set()
            additional_words = set(str(gpt_row['Keywords']).lower().split(',')) if 'Keywords' in gpt_row and pd.notna(gpt_row['Keywords']) else set()

            combined_words = title_words.union(subtitle_words).union(additional_words)
            print(f"\033[35mDEBUG: İşlenen Title_Subtitle satırı {gpt_idx}, Kelimeler: {combined_words}\033[0m")

            matched_keywords = []
            total_volume = 0
            total_difficulty = 0
            ort_volume = 0
            ort_difficulty = 0
            counter = 0

            for _, merged_row in merged_df.iterrows():
                keyword_value = merged_row.get('Keyword')

                if pd.isna(keyword_value) or not isinstance(keyword_value, str):
                    continue
                
                keyword_words = set(keyword_value.lower().split())

                if keyword_words.issubset(combined_words):
                    matched_keywords.append(keyword_value)
                    total_volume += merged_row['Volume']
                    total_difficulty += merged_row['Difficulty']
                    counter += 1
                    ort_difficulty = round(total_difficulty / counter, 3)
                    ort_volume = round(total_volume / counter, 3)
                    matched_keywords_result.append({
                        'Matched Keywords': merged_row['Keyword'],
                        'Volume': merged_row['Volume'],
                        'Difficulty': merged_row['Difficulty']
                    })

                    print(f"\033[32mDEBUG: Eşleşme! '{keyword_value}' (Vol: {merged_row['Volume']}, Diff: {merged_row['Difficulty']})\033[0m")
            
            results.append({
                'Title': gpt_row['Title'],
                'Subtitle': gpt_row['Subtitle'],
                'Keywords': gpt_row['Keywords'],
                'Title Lenght': gpt_row['Title_Lenght'],
                'Subtitle Lenght': gpt_row['Subtitle_Lenght'],
                'Keywords Lenght': gpt_row['Keywords_Lenght'],
                'Total Volume': total_volume,
                'Total Difficulty': total_difficulty,
                'Avarage Volume': ort_volume,
                'Avarage Difficulty': ort_difficulty,
                'Renklenen Keywords Sayısı': counter
            })

        print(f"\033[34mDEBUG: find_matching_keywords() tamamlandı.\033[0m")
        return pd.DataFrame(results), pd.DataFrame(matched_keywords_result)

# Flet ASO App
class ASOApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "ASO Generate Tool - Professional Edition"
        self.page.theme_mode = ThemeMode.LIGHT
        self.page.window_width = 1600
        self.page.window_height = 900
        self.page.window_min_width = 800  # Daha küçük cihazlar için
        self.page.window_min_height = 600  # Daha küçük cihazlar için
        self.page.window_resizable = True
        self.page.window_maximizable = True
        self.page.padding = 20
        
        # Veri storage
        self.folder_path = ""
        self.difficulty_limit = 20
        self.growth_limit = 0
        self.selected_country = "United States"
        self.selected_category = "Tümü"
        self.selected_country_filter = "Tümü"
        self.app_name = ""
        self.open_ai_key = open_ai_key
        
        # DataFrame'ler
        self.merged_noduplicate_df = None
        self.kvd_df = None
        self.kelime_frekans_df = None
        self.without_branded_df = None
        self.without_suffixes_df = None
        self.gpt_title_subtitle_df = None
        self.matching_keywords_df_ts = None
        self.matching_keywords_df = None
        self.current_table = None
        
        self.setup_ui()
        
    def setup_ui(self):
        # Ana container
        main_container = ft.Container(
            content=ft.Column([
                # Header
                ft.Container(
                    content=ft.Row([
                        ft.Icon(Icons.ANALYTICS, size=30, color=Colors.BLUE_700),
                        ft.Text(
                            "ASO Generate Tool",
                            size=28,
                            weight=FontWeight.BOLD,
                            color=Colors.BLUE_700
                        ),
                        ft.Text(
                            "Professional Edition",
                            size=16,
                            color=Colors.GREY_600,
                            style=ft.TextThemeStyle.BODY_MEDIUM
                        )
                    ]),
                    bgcolor=Colors.BLUE_50,
                    padding=20,
                    border_radius=10,
                    margin=ft.margin.only(bottom=20)
                ),
                
                # Main content - Responsive Layout
                ft.Container(
                    content=ft.Row([
                        # Left Panel - Controls (30% genişlik)
                        ft.Container(
                            content=self.create_left_panel(),
                            bgcolor=Colors.WHITE,
                            border_radius=10,
                            padding=20,
                            expand=3,  # 30% ekran genişliği
                            shadow=ft.BoxShadow(
                                spread_radius=1,
                                blur_radius=10,
                                color=Colors.with_opacity(0.1, Colors.GREY_400)
                            )
                        ),
                        
                        # Spacing
                        ft.Container(width=20),
                        
                        # Right Panel - Table (70% genişlik)
                        ft.Container(
                            content=self.create_right_panel(),
                            bgcolor=Colors.WHITE,
                            border_radius=10,
                            padding=20,
                            expand=7,  # 70% ekran genişliği
                            shadow=ft.BoxShadow(
                                spread_radius=1,
                                blur_radius=10,
                                color=Colors.with_opacity(0.1, Colors.GREY_400)
                            )
                        )
                    ], 
                    alignment=ft.MainAxisAlignment.START,
                    expand=True)
                )
            ], expand=True),
            expand=True
        )
        
        self.page.add(main_container)
        
    def create_left_panel(self):
        # File picker
        self.folder_picker = ft.FilePicker(on_result=self.on_folder_selected)
        self.page.overlay.append(self.folder_picker)
        
        # Folder selection area - Responsive
        self.folder_display = ft.Container(
            content=ft.Column([
                ft.Icon(Icons.FOLDER_OPEN, size=40, color=Colors.BLUE_400),
                ft.Text(
                    "CSV Klasörü Seç",
                    size=16,
                    text_align=ft.TextAlign.CENTER,
                    color=Colors.BLUE_600
                ),
                ft.Text(
                    "Klasör seçmek için tıklayın",
                    size=12,
                    text_align=ft.TextAlign.CENTER,
                    color=Colors.GREY_600
                )
            ], alignment=ft.MainAxisAlignment.CENTER),
            height=120,
            bgcolor=Colors.BLUE_50,
            border=ft.border.all(2, Colors.BLUE_200),
            border_radius=10,
            padding=20,
            alignment=ft.alignment.center,
            expand=True,  # Responsive genişlik
            on_click=lambda _: self.folder_picker.get_directory_path()
        )
        

        
        # Filtre bölgesi
        filter_title = ft.Text(
            "🔍 Filtre Ayarları",
            size=16,
            weight=FontWeight.BOLD,
            color=Colors.BLUE_700
        )
        
        # Difficulty filter
        self.difficulty_filter_input = ft.TextField(
            label="Difficulty Sınırı",
            value="20",
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=self.on_difficulty_filter_changed,
            expand=True
        )
        
        # Growth filter
        self.growth_input = ft.TextField(
            label="Growth Sınırı",
            value="0",
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=self.on_growth_changed,
            expand=True
        )
        
        # Category filter dropdown
        self.category_dropdown = ft.Dropdown(
            label="Kategori Filtresi",
            value="Tümü",
            options=[
                ft.dropdown.Option("Tümü"),
                ft.dropdown.Option("Photo & Video"),
                ft.dropdown.Option("Productivity"),
                ft.dropdown.Option("Music"),
                ft.dropdown.Option("Health & Fitness")
            ],
            on_change=self.on_category_changed,
            expand=True
        )
        
        # Country filter dropdown
        self.country_filter_dropdown = ft.Dropdown(
            label="Ülke Filtresi",
            value="Tümü",
            options=[
                ft.dropdown.Option("Tümü"),
                ft.dropdown.Option("United States"),
                ft.dropdown.Option("United Kingdom"),
                ft.dropdown.Option("Germany"),
                ft.dropdown.Option("France"),
                ft.dropdown.Option("Japan"),
                ft.dropdown.Option("Canada"),
                ft.dropdown.Option("Australia")
            ],
            on_change=self.on_country_filter_changed,
            expand=True
        )
        
        # Apply filters button
        self.apply_filters_button = ft.ElevatedButton(
            "🔍 Filtreleri Uygula",
            on_click=self.apply_filters,
            style=ft.ButtonStyle(
                color=Colors.WHITE,
                bgcolor=Colors.GREEN_600,
                elevation=2,
                shape=ft.RoundedRectangleBorder(radius=8)
            ),
            height=45,
            expand=True
        )
        
        # Buttons
        button_style = ft.ButtonStyle(
            color=Colors.WHITE,
            bgcolor=Colors.BLUE_600,
            elevation=2,
            shape=ft.RoundedRectangleBorder(radius=8)
        )
        
        # Responsive Buttons
        buttons = [
            ft.ElevatedButton(
                "Birleştirilmiş Ana Tablo",
                on_click=self.show_merged_table,
                style=button_style,
                height=45,
                expand=True  # Responsive genişlik
            ),
            ft.ElevatedButton(
                "Keyword Volume Difficulty",
                on_click=self.show_kvd_table,
                style=button_style,
                height=45,
                expand=True  # Responsive genişlik
            ),
            ft.ElevatedButton(
                "Kelime Frekansı",
                on_click=self.show_frequency_table,
                style=button_style,
                height=45,
                expand=True  # Responsive genişlik
            ),
            ft.ElevatedButton(
                "Branded Kelimeler Filtrelenmiş",
                on_click=self.show_branded_filtered_table,
                style=button_style,
                height=45,
                expand=True  # Responsive genişlik
            ),
            ft.ElevatedButton(
                "Eklerden Ayrılmış Kelimeler",
                on_click=self.show_suffixes_removed_table,
                style=button_style,
                height=45,
                expand=True  # Responsive genişlik
            ),
            ft.ElevatedButton(
                "Title Subtitle Analiz",
                on_click=self.show_title_subtitle_table,
                style=button_style,
                height=45,
                expand=True  # Responsive genişlik
            )
        ]
        
        return ft.Column([
            self.folder_display,
            ft.Divider(height=20),
            ft.ElevatedButton(
                "Yükle",
                on_click=self.load_data,
                style=ft.ButtonStyle(
                    color=Colors.WHITE,
                    bgcolor=Colors.GREEN_600,
                    elevation=2,
                    shape=ft.RoundedRectangleBorder(radius=8)
                ),
                height=45,
                expand=True  # Responsive genişlik
            ),
            ft.Divider(height=20),
            # Filtre bölgesi için scroll container
            ft.Container(
                content=ft.Column([
                    filter_title,
                    ft.Divider(height=10),
                    ft.Row([
                        self.difficulty_filter_input,
                        ft.Container(width=10),
                        self.growth_input
                    ]),
                    ft.Divider(height=10),
                    ft.Row([
                        self.category_dropdown,
                        ft.Container(width=10),
                        self.country_filter_dropdown
                    ]),
                    ft.Divider(height=10),
                    self.apply_filters_button,
                    ft.Container(height=10)  # Bottom padding
                ], spacing=5, scroll=ScrollMode.ALWAYS),
                height=200,  # Sabit yükseklik
                border=ft.border.all(1, Colors.BLUE_200),
                border_radius=8,
                padding=10,
                bgcolor=Colors.BLUE_50
            ),
            ft.Divider(height=20),
            # Butonlar için ayrı scroll container
            ft.Container(
                content=ft.Column([
                    *buttons,
                    ft.Container(height=20)  # Bottom padding
                ], spacing=10, scroll=ScrollMode.ALWAYS),  # Scroll aktif
                height=300,  # Sabit yükseklik
                border=ft.border.all(1, Colors.GREY_200),
                border_radius=8,
                padding=10,
                bgcolor=Colors.GREY_50
            )
        ], spacing=10, expand=True)
    
    def create_right_panel(self):
        # Table title
        self.table_title = ft.Text(
            "Tablo",
            size=20,
            weight=FontWeight.BOLD,
            color=Colors.BLUE_700
        )
        
        # Data table - Responsive
        self.data_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Tablo", weight=FontWeight.BOLD))
            ],
            rows=[
                ft.DataRow(cells=[ft.DataCell(ft.Text("Veri yüklendikten sonra tablolar burada görünecek"))])
            ],
            border=ft.border.all(1, Colors.GREY_300),
            border_radius=10,
            vertical_lines=ft.border.BorderSide(1, Colors.GREY_300),
            horizontal_lines=ft.border.BorderSide(1, Colors.GREY_300),
            heading_row_color=Colors.BLUE_50,
            heading_row_height=50,
            column_spacing=20,  # Küçültüldü responsive için
            show_checkbox_column=False,
            divider_thickness=1
            # width kaldırıldı - responsive olacak
        )
        
        # Table container - Responsive with horizontal and vertical scrolling
        table_container = ft.Container(
            content=ft.Row([
                ft.Column([
                    self.data_table
                ], scroll=ScrollMode.AUTO),
            ], scroll=ScrollMode.AUTO),
            height=350,  # Yükseklik azaltıldı
            border=ft.border.all(1, Colors.GREY_300),
            border_radius=10,
            padding=10,
            expand=True  # Responsive genişlik
        )
        
        # Dosya adı girişi
        self.filename_input = ft.TextField(
            label="Dosya Adı (isteğe bağlı)",
            hint_text="aso_table",
            value="",
            expand=True,
            height=45
        )
        
        # Export button - Responsive
        self.export_button = ft.ElevatedButton(
            "📥 Excel İndir",
            on_click=self.export_table,
            style=ft.ButtonStyle(
                color=Colors.WHITE,
                bgcolor=Colors.ORANGE_600,
                elevation=2,
                shape=ft.RoundedRectangleBorder(radius=8)
            ),
            height=45,
            width=150
        )
        
        return ft.Column([
            self.table_title,
            ft.Divider(height=10),
            table_container,
            ft.Divider(height=10),
            # Export bölümü - Daha üstte
            ft.Container(
                content=ft.Column([
                    ft.Text(
                        "📁 Dosya İndirme",
                        size=14,
                        weight=FontWeight.BOLD,
                        color=Colors.BLUE_700
                    ),
                    ft.Row([
                        self.filename_input,
                        ft.Container(width=10),
                        self.export_button
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
                ], spacing=5),
                bgcolor=Colors.ORANGE_50,
                border=ft.border.all(1, Colors.ORANGE_200),
                border_radius=8,
                padding=15,
                margin=ft.margin.only(bottom=10)
            )
        ], spacing=5, expand=True)
    
    # Event handlers
    def on_folder_selected(self, e: ft.FilePickerResultEvent):
        if e.path:
            self.folder_path = e.path
            self.folder_display.content = ft.Column([
                ft.Icon(Icons.FOLDER, size=40, color=Colors.GREEN_600),
                ft.Text(
                    "Klasör Seçildi",
                    size=16,
                    text_align=ft.TextAlign.CENTER,
                    color=Colors.GREEN_600
                ),
                ft.Text(
                    os.path.basename(e.path),
                    size=12,
                    text_align=ft.TextAlign.CENTER,
                    color=Colors.GREY_600
                )
            ], alignment=ft.MainAxisAlignment.CENTER)
            self.folder_display.bgcolor = Colors.GREEN_50
            self.folder_display.border = ft.border.all(2, Colors.GREEN_200)
            self.page.update()
    

    
    def on_difficulty_filter_changed(self, e):
        try:
            self.difficulty_limit = float(e.control.value)
        except ValueError:
            self.difficulty_limit = 20
    
    def on_growth_changed(self, e):
        try:
            self.growth_limit = float(e.control.value)
        except ValueError:
            self.growth_limit = 0
    
    def on_category_changed(self, e):
        self.selected_category = e.control.value
    
    def on_country_filter_changed(self, e):
        self.selected_country_filter = e.control.value
    
    def apply_filters(self, e):
        """Filtreleri uygular ve mevcut tabloyu günceller"""
        if self.merged_noduplicate_df is None:
            self.show_warning("Önce verileri yükleyin!")
            return
        
        try:
            # Filtrelenmiş DataFrame oluştur
            filtered_df = self.merged_noduplicate_df.copy()
            
            # Difficulty filtresi
            if self.difficulty_limit > 0:
                filtered_df = filtered_df[filtered_df['Difficulty'] <= self.difficulty_limit]
            
            # Growth filtresi (eğer Growth sütunu varsa)
            if self.growth_limit > 0 and 'Growth' in filtered_df.columns:
                filtered_df = filtered_df[filtered_df['Growth'] >= self.growth_limit]
            
            # Kategori filtresi
            if self.selected_category != "Tümü":
                filtered_df = filtered_df[filtered_df['Category'] == self.selected_category]
            
            # Ülke filtresi (eğer Country sütunu varsa)
            if self.selected_country_filter != "Tümü" and 'Country' in filtered_df.columns:
                filtered_df = filtered_df[filtered_df['Country'] == self.selected_country_filter]
            
            # Filtrelenmiş veriyi göster
            if filtered_df.empty:
                self.show_warning("Filtre kriterlerine uygun veri bulunamadı!")
                return
            
            self.display_dataframe(filtered_df, f"Filtrelenmiş Tablo ({len(filtered_df)} kayıt)")
            self.current_table = filtered_df
            
            self.show_success(f"Filtreler uygulandı! {len(filtered_df)} kayıt gösteriliyor.")
            
        except Exception as ex:
            self.show_error(f"Filtre uygulama hatası: {str(ex)}")
    
    def load_data(self, e):
        if not self.folder_path:
            self.show_error("Lütfen önce bir klasör seçin!")
            return
        
        try:
            # Show loading
            self.show_loading("Veriler yükleniyor...")
            
            # Load data
            self.merged_noduplicate_df = Df_Get.merged_noduplicate_df(self.folder_path)
            self.kvd_df = Df_Get.kvd_df(self.merged_noduplicate_df, self.difficulty_limit)
            self.kelime_frekans_df = Df_Get.kelime_frekans_df(self.kvd_df, self.open_ai_key)
            self.without_branded_df = Df_Get.without_branded_kf_df_get(self.kelime_frekans_df, self.open_ai_key)
            
            self.hide_loading()
            self.show_success("Veriler başarıyla yüklendi!")
            
        except Exception as ex:
            self.hide_loading()
            self.show_error(f"Veri yükleme hatası: {str(ex)}")
    
    def show_merged_table(self, e):
        if self.merged_noduplicate_df is None:
            # Test için sample CSV'leri otomatik yükle
            try:
                sample_path = "/Users/halenuryesilova/Downloads/ASO_Generator_Tool/sample_CSV_archive"
                self.folder_path = sample_path
                self.show_loading("Test verileri yükleniyor...")
                self.merged_noduplicate_df = Df_Get.merged_noduplicate_df(sample_path)
                self.hide_loading()
                self.show_success("Test verileri yüklendi!")
            except Exception as ex:
                self.hide_loading()
                self.show_error(f"Test veri yükleme hatası: {str(ex)}")
                return
        
        self.display_dataframe(self.merged_noduplicate_df, "Birleştirilmiş Ana Tablo")
        self.current_table = self.merged_noduplicate_df
    
    def show_kvd_table(self, e):
        if self.kvd_df is None:
            # Önce merged_df'i yükle
            if self.merged_noduplicate_df is None:
                try:
                    sample_path = "/Users/halenuryesilova/Downloads/ASO_Generator_Tool/sample_CSV_archive"
                    self.folder_path = sample_path
                    self.show_loading("Test verileri yükleniyor...")
                    self.merged_noduplicate_df = Df_Get.merged_noduplicate_df(sample_path)
                    self.hide_loading()
                except Exception as ex:
                    self.hide_loading()
                    self.show_error(f"Veri yükleme hatası: {str(ex)}")
                    return
            
            # KVD tablosunu oluştur
            try:
                self.show_loading("KVD tablosu oluşturuluyor...")
                self.kvd_df = Df_Get.kvd_df(self.merged_noduplicate_df, self.difficulty_limit)
                self.hide_loading()
            except Exception as ex:
                self.hide_loading()
                self.show_error(f"KVD tablo oluşturma hatası: {str(ex)}")
                return
        
        self.display_dataframe(self.kvd_df, "Keyword Volume Difficulty Tablosu")
        self.current_table = self.kvd_df
    
    def show_frequency_table(self, e):
        if self.kelime_frekans_df is None:
            self.show_warning("Önce verileri yükleyin!")
            return
        
        self.display_dataframe(self.kelime_frekans_df, "Kelime Frekans Tablosu")
        self.current_table = self.kelime_frekans_df
    
    def show_branded_filtered_table(self, e):
        if self.without_branded_df is None:
            self.show_warning("Önce verileri yükleyin!")
            return
        
        self.display_dataframe(self.without_branded_df, "Branded Kelimeler Filtrelenmiş Tablo")
        self.current_table = self.without_branded_df
    
    def show_suffixes_removed_table(self, e):
        if self.merged_noduplicate_df is None:
            self.show_warning("Önce verileri yükleyin!")
            return
        
        try:
            self.show_loading("Ekler kaldırılıyor...")
            self.without_suffixes_df = Df_Get.without_suffixes_df_get(
                self.without_branded_df, "United States", self.open_ai_key
            )
            self.hide_loading()
            
            self.display_dataframe(self.without_suffixes_df, "Eklerden Ayrılmış Kelimeler")
            self.current_table = self.without_suffixes_df
            
        except Exception as ex:
            self.hide_loading()
            self.show_error(f"Ek kaldırma hatası: {str(ex)}")
    
    def show_title_subtitle_table(self, e):
        if self.without_suffixes_df is None:
            self.show_warning("Önce eklerden ayrılmış kelime tablosunu oluşturun!")
            return
        
        try:
            self.show_loading("Title ve Subtitle oluşturuluyor...")
            
            self.gpt_title_subtitle_df = Df_Get.gpt_Title_Subtitle_df_get(
                self.without_suffixes_df, "App Name", "United States", self.open_ai_key
            )
            
            if self.gpt_title_subtitle_df.empty:
                self.difficulty_limit += 10
                self.page.update()
                self.load_data(None)
                return self.show_title_subtitle_table(e)
            
            self.matching_keywords_df_ts, self.matching_keywords_df = Df_Get.find_matching_keywords(
                self.gpt_title_subtitle_df, self.merged_noduplicate_df
            )
            
            self.hide_loading()
            self.display_dataframe(self.matching_keywords_df_ts, "Title Subtitle Analiz Tablosu")
            self.current_table = self.matching_keywords_df_ts
            
        except Exception as ex:
            self.hide_loading()
            self.show_error(f"Title/Subtitle oluşturma hatası: {str(ex)}")
    
    def display_dataframe(self, df: pd.DataFrame, title: str):
        if df is None or df.empty:
            self.show_warning("Tablo boş!")
            return
        
        # Update table title
        self.table_title.value = title
        
        # Clear existing data
        self.data_table.columns.clear()
        self.data_table.rows.clear()
        
        # Add columns with dynamic width
        for col in df.columns:
            # Title sütunu için özel genişlik
            if col == 'Title':
                column_width = 120
            elif col == 'Keyword':
                column_width = 200
            elif col in ['Volume', 'Difficulty', 'Frekans']:
                column_width = 100
            else:
                column_width = 150
                
            self.data_table.columns.append(
                ft.DataColumn(
                    ft.Text(
                        str(col),
                        size=12,
                        weight=FontWeight.BOLD,
                        color=Colors.BLUE_700
                    )
                )
            )
        
        # Add rows (limit to first 100 rows for performance)
        for idx, row in df.head(100).iterrows():
            cells = []
            for value in row:
                cells.append(
                    ft.DataCell(
                        ft.Text(
                            str(value),
                            size=11,
                            color=Colors.BLACK87
                        )
                    )
                )
            self.data_table.rows.append(ft.DataRow(cells=cells))
        
        self.page.update()
    
    def export_table(self, e):
        if self.current_table is None:
            self.show_warning("Dışa aktarılacak tablo yok!")
            return
        
        try:
            # Kullanıcının girdiği dosya adını al, yoksa varsayılan ad kullan
            custom_filename = self.filename_input.value.strip()
            if custom_filename:
                # Güvenli dosya adı oluştur (özel karakterleri temizle)
                import re
                safe_filename = re.sub(r'[<>:"/\\|?*]', '_', custom_filename)
                base_filename = safe_filename
            else:
                base_filename = "aso_table"
            
            # Timestamp ekle
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{base_filename}_{timestamp}.xlsx"
            
            self.show_loading(f"Excel dosyası hazırlanıyor: {filename}")
            
            # Create Excel file in memory
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                self.current_table.to_excel(writer, index=False, sheet_name='ASO Data')
            
            excel_data = buffer.getvalue()
            
            # Save to project directory and Desktop
            project_path = os.path.join(os.getcwd(), filename)
            desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", filename)
            
            # Save Excel files
            with open(project_path, 'wb') as f:
                f.write(excel_data)
            
            try:
                with open(desktop_path, 'wb') as f:
                    f.write(excel_data)
                self.hide_loading()
                self.show_success(f"✅ Excel dosyası kaydedildi!\n📁 Proje: {filename}\n🖥️ Masaüstü: {filename}")
            except PermissionError:
                self.hide_loading()
                self.show_success(f"✅ Excel dosyası proje klasörüne kaydedildi: {filename}")
            
            # Dosya adı alanını temizle
            self.filename_input.value = ""
            self.page.update()
            
        except Exception as ex:
            self.hide_loading()
            # Excel başarısız olursa CSV'ye geç
            try:
                custom_filename = self.filename_input.value.strip()
                if custom_filename:
                    import re
                    safe_filename = re.sub(r'[<>:"/\\|?*]', '_', custom_filename)
                    base_filename = safe_filename
                else:
                    base_filename = "aso_table"
                
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                csv_filename = f"{base_filename}_{timestamp}.csv"
                csv_project_path = os.path.join(os.getcwd(), csv_filename)
                csv_desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", csv_filename)
                
                # Save CSV files
                self.current_table.to_csv(csv_project_path, index=False)
                
                try:
                    self.current_table.to_csv(csv_desktop_path, index=False)
                    self.show_warning(f"⚠️ Excel başarısız, CSV kaydedildi!\n📁 Proje: {csv_filename}\n🖥️ Masaüstü: {csv_filename}")
                except PermissionError:
                    self.show_warning(f"⚠️ Excel başarısız, CSV proje klasörüne kaydedildi: {csv_filename}")
                
                # Dosya adı alanını temizle
                self.filename_input.value = ""
                self.page.update()
                    
            except Exception as csv_ex:
                self.show_error(f"❌ Dosya kaydetme başarısız: {str(csv_ex)}")
                # Dosya adı alanını temizle
                self.filename_input.value = ""
                self.page.update()
    
    # Utility methods
    def show_loading(self, message: str):
        self.page.splash = ft.ProgressBar()
        self.page.update()
    
    def hide_loading(self):
        self.page.splash = None
        self.page.update()
    
    def show_error(self, message: str):
        self.page.show_snack_bar(
            ft.SnackBar(
                content=ft.Text(message, color=Colors.WHITE),
                bgcolor=Colors.RED_600
            )
        )
    
    def show_warning(self, message: str):
        self.page.show_snack_bar(
            ft.SnackBar(
                content=ft.Text(message, color=Colors.WHITE),
                bgcolor=Colors.ORANGE_600
            )
        )
    
    def show_success(self, message: str):
        self.page.show_snack_bar(
            ft.SnackBar(
                content=ft.Text(message, color=Colors.WHITE),
                bgcolor=Colors.GREEN_600
            )
        )

def main(page: ft.Page):
    ASOApp(page)

if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.WEB_BROWSER) 
