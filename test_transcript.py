from youtube_transcript_api import YouTubeTranscriptApi

# Test with a well-known YouTube video
video_id = "jNQXAC9IVRw"  # YouTube's first ever video

try:
    transcript = YouTubeTranscriptApi.get_transcript(video_id)
    print(f"✓ Successfully fetched {len(transcript)} transcript entries")
    print(f"\nFirst 3 entries:")
    for i, entry in enumerate(transcript[:3]):
        print(f"  {i+1}. [{entry['start']:.1f}s] {entry['text'][:60]}...")
except Exception as e:
    print(f"✗ Error: {e}")
