#!/usr/bin/env python3
"""
Test script to check which YouTube videos have transcripts available
"""

from youtube_transcript_api import YouTubeTranscriptApi
import sys

def test_video(video_id):
    """Test if a video has transcripts available"""
    try:
        transcripts = YouTubeTranscriptApi.list_transcripts(video_id)

        # Try English
        try:
            transcript = transcripts.find_transcript(['en', 'en-US'])
            data = transcript.fetch()
            print(f"✓ {video_id}: {len(data)} English segments")
            return True
        except:
            pass

        # Try any language
        try:
            # Get first available
            all_transcripts = []
            if hasattr(transcripts, '_manually_created_transcripts'):
                all_transcripts = transcripts._manually_created_transcripts
            elif hasattr(transcripts, '_generated_transcripts'):
                all_transcripts = transcripts._generated_transcripts

            if all_transcripts:
                data = all_transcripts[0].fetch()
                lang = getattr(all_transcripts[0], 'language', 'Unknown')
                print(f"✓ {video_id}: {len(data)} segments ({lang})")
                return True
        except:
            pass

        print(f"✗ {video_id}: No transcripts available")
        return False

    except Exception as e:
        print(f"✗ {video_id}: Error - {type(e).__name__}")
        return False

if __name__ == "__main__":
    print("YouTube Transcript Availability Checker")
    print("=" * 60)

    # Test with video IDs provided as arguments
    if len(sys.argv) > 1:
        for video_id in sys.argv[1:]:
            test_video(video_id)
    else:
        # Test with some example videos
        print("Usage: python3 test_videos.py <video_id1> <video_id2> ...")
        print("\nTesting some example videos:")
        print("=" * 60)

        example_videos = [
            "dQw4w9WgXcQ",      # Rick Roll
            "hWIjko3ilns",      # User provided video
            "Lf3qNlJaYQA",      # MKBHD recent video (should have transcript)
        ]

        for vid in example_videos:
            test_video(vid)
