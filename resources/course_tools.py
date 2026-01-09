import os
import json
import isodate  # Required for parsing YouTube durations
from datetime import timedelta
from openai import OpenAI, OpenAIError, RateLimitError
from googleapiclient.discovery import build  # Standard YouTube API client
from django.core.exceptions import ValidationError

# 1. Initialize Clients
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY')

# Initialize DeepSeek client (OpenAI-compatible)
deepseek_client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

# Initialize YouTube Service
youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)


def _call_deepseek_api(prompt: str):
    """
    Call DeepSeek API with proper JSON response formatting
    """
    try:
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",  # Use "deepseek-coder" if course is programming-related
            messages=[
                {
                    "role": "system",
                    "content": "You are a Senior Curriculum Designer. Always respond with valid JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=2000
        )

        content = response.choices[0].message.content
        return json.loads(content)

    except RateLimitError:
        return {
            "improved_title": "AI Busy (Rate Limit Hit)",
            "enriched_description": "High demand. Please try again later.",
            "modules": []
        }
    except json.JSONDecodeError as e:
        # Fallback in case AI doesn't return valid JSON
        print(f"JSON parsing error: {e}")
        return {
            "improved_title": "Course Title",
            "enriched_description": "Course Description",
            "modules": []
        }
    except OpenAIError as e:
        print(f"DeepSeek API Error: {e}")
        raise e


def _construct_search_query(course_title: str, module_title: str) -> str:
    """
    Construct a high-quality YouTube search query for educational content
    """
    # Add educational keywords for better relevance
    educational_keywords = [
        "tutorial", "explained", "guide", "beginners",
        "step by step", "full course", "lecture"
    ]

    # Use the module title primarily, with course title as context
    base_query = f"{module_title} {course_title}"

    # Add the most relevant educational keyword
    query = f"{base_query} tutorial"

    # Clean up query: remove extra spaces, special characters
    query = ' '.join(query.split())
    return query[:100]  # YouTube API limit for query length


def _fetch_youtube_content(course_title: str, module_title: str):
    """
    Enhanced YouTube API implementation with better search parameters
    """
    try:
        # Construct optimized search query
        search_query = _construct_search_query(course_title, module_title)

        print(f"Searching YouTube for: {search_query}")  # Debug logging

        # 1. Search for video IDs with optimized parameters
        search_response = youtube.search().list(
            q=search_query,
            part='snippet',
            maxResults=5,  # Get more results to filter later
            type='video',
            videoEmbeddable='true',
            relevanceLanguage='en',
            videoDuration='medium',  # Filter for medium length videos (4-20 min)
            order='relevance',  # Most relevant first
            safeSearch='moderate',  # Filter out inappropriate content
            videoDefinition='high',  # Prefer HD videos
            fields='items(id(videoId),snippet(title,channelTitle))'  # Limit response size
        ).execute()

        video_items = search_response.get('items', [])
        if not video_items:
            print(f"No videos found for query: {search_query}")
            return []

        # Extract video IDs
        video_ids = [item['id']['videoId'] for item in video_items if item['id'].get('videoId')]

        if not video_ids:
            return []

        # 2. Get detailed metadata including duration and statistics
        video_details = youtube.videos().list(
            id=','.join(video_ids),
            part='contentDetails,snippet,statistics',
            fields='items(id,snippet(title,channelTitle),contentDetails(duration),statistics(viewCount))'
        ).execute()

        results = []
        for item in video_details.get('items', []):
            try:
                # Parse ISO 8601 duration
                dur_raw = item['contentDetails']['duration']
                dur_seconds = int(isodate.parse_duration(dur_raw).total_seconds())

                # Filter for educational content: 2 to 60 minutes
                if not (120 <= dur_seconds <= 3600):
                    continue

                # Format duration for display
                minutes, seconds = divmod(dur_seconds, 60)
                duration_str = f"{minutes} min {seconds} sec" if seconds > 0 else f"{minutes} min"

                # Get view count for quality filtering
                view_count = int(item['statistics'].get('viewCount', 0))

                # Calculate quality score (simplified)
                quality_score = view_count / 1000  # Simple heuristic

                results.append({
                    'title': item['snippet']['title'][:100],  # Truncate long titles
                    'url': f"https://www.youtube.com/embed/{item['id']}",
                    'watch_url': f"https://www.youtube.com/watch?v={item['id']}",
                    'duration': duration_str,
                    'duration_seconds': dur_seconds,
                    'channel': item['snippet'].get('channelTitle', 'Unknown'),
                    'views': view_count,
                    'quality_score': quality_score
                })
            except (KeyError, ValueError) as e:
                print(f"Skipping video due to parsing error: {e}")
                continue

        # Sort by quality score (views) and duration relevance
        results.sort(key=lambda x: x['quality_score'], reverse=True)

        # Return top 2-3 most relevant videos
        return results[:3]

    except Exception as e:
        print(f"YouTube API Error: {e}")
        # Return empty list to prevent breaking the flow
        return []


def generate_course_roadmap(course):
    """
    Main function to generate course roadmap using DeepSeek and YouTube API
    """
    # Prepare prompt for DeepSeek
    prompt = f"""
    As a Senior Curriculum Designer, transform this course into a structured learning path.

    Original Course:
    Title: {course.title}
    Description: {course.description}

    Please provide a JSON response with this structure:
    {{
        "improved_title": "Enhanced course title",
        "enriched_description": "Detailed course description (2-3 paragraphs)",
        "modules": [
            {{
                "title": "Module title",
                "description": "Module description",
                "objectives": ["Objective 1", "Objective 2", "Objective 3"]
            }}
        ]
    }}

    Requirements:
    1. Create 4-6 modules for a comprehensive learning path
    2. Each module should focus on a specific topic
    3. Include clear learning objectives for each module
    4. Ensure the course title is compelling and SEO-friendly
    5. The description should be detailed and informative
    """

    # Get AI-generated course structure
    ai_raw_data = _call_deepseek_api(prompt)

    total_seconds = 0
    structured_modules = []

    # Process each module and fetch relevant YouTube videos
    for module_data in ai_raw_data.get('modules', []):
        # Fetch relevant YouTube videos for this module
        videos = _fetch_youtube_content(
            course_title=ai_raw_data.get('improved_title', course.title),
            module_title=module_data['title']
        )

        # Calculate module duration
        module_seconds = sum(v['duration_seconds'] for v in videos)

        # Add video data to module
        module_data['videos'] = videos
        module_data['duration_seconds'] = module_seconds
        module_data['video_count'] = len(videos)

        total_seconds += module_seconds
        structured_modules.append(module_data)

    # Update course model
    course.title = ai_raw_data.get('improved_title', course.title)
    course.description = ai_raw_data.get('enriched_description', course.description)
    course.estimated_duration = timedelta(seconds=total_seconds)
    course.roadmap_json = json.dumps(structured_modules, indent=2)
    course.save()

    return structured_modules


def get_fallback_videos(module_title: str):
    """
    Get fallback videos when YouTube API fails or returns no results
    """
    # You can implement:
    # 1. Cached video database
    # 2. Alternative video sources
    # 3. Placeholder content
    return [{
        'title': f'Introduction to {module_title}',
        'url': 'https://www.youtube.com/embed/dQw4w9WgXcQ',  # Example video
        'watch_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
        'duration': '10 min',
        'duration_seconds': 600,
        'channel': 'Educational Channel',
        'views': 1000000,
        'quality_score': 1000
    }]