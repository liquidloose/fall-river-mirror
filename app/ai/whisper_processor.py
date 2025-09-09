import os
import tempfile
import logging
import shutil
import subprocess
from typing import Optional
import yt_dlp
from openai import OpenAI

logger = logging.getLogger(__name__)


class WhisperProcessor:
    """Handles OpenAI Whisper-based audio transcription for YouTube videos."""

    def __init__(self, video_id: Optional[str] = None):
        self.video_id = video_id
        self.api_key = os.getenv("OPENAI_API_KEY")
        """
        Initialize WhisperProcessor.

        Args:
            video_id: YouTube video ID
        """

        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable or api_key parameter is required"
            )

        self.client = OpenAI(api_key=self.api_key)
        self.max_file_size = 25 * 1024 * 1024  # 25MB in bytes
        self.chunk_duration = 1200  # 20 minutes in seconds

    def transcribe_youtube_video(self, video_id: str) -> str:
        """
        Download YouTube video and transcribe using OpenAI Whisper API.

        Args:
            video_id: YouTube video ID

        Returns:
            str: Transcribed text

        Raises:
            Exception: If transcription fails
        """
        temp_dir = None

        try:
            # Create temporary directory
            temp_dir = tempfile.mkdtemp()
            audio_file_path = os.path.join(temp_dir, f"{video_id}.%(ext)s")

            # Download audio from YouTube video with compression
            ydl_opts = {
                "format": "bestaudio[filesize<25M]/best[filesize<25M]/bestaudio/best",
                "outtmpl": audio_file_path,
                "audioquality": "96K",  # Lower bitrate to reduce file size
                "noplaylist": True,
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "96",
                    }
                ],
            }

            youtube_url = f"https://www.youtube.com/watch?v={video_id}"

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.info(f"Downloading audio for video: {video_id}")
                ydl.download([youtube_url])

            # Find the actual downloaded file (yt-dlp changes extension)
            downloaded_files = [
                f for f in os.listdir(temp_dir) if f.startswith(video_id)
            ]
            if not downloaded_files:
                raise Exception("No audio file was downloaded")

            actual_audio_path = os.path.join(temp_dir, downloaded_files[0])

            # Check file size and split if needed
            file_size = os.path.getsize(actual_audio_path)

            if file_size > self.max_file_size:
                logger.info(
                    f"Audio file is {file_size / 1024 / 1024:.1f}MB, splitting into chunks"
                )
                transcript_text = self._transcribe_large_file(
                    actual_audio_path, video_id, temp_dir
                )
            else:
                logger.info(
                    f"Audio file is {file_size / 1024 / 1024:.1f}MB, transcribing directly"
                )
                transcript_text = self._transcribe_single_file(
                    actual_audio_path, video_id
                )

            return transcript_text

        except Exception as e:
            logger.error(
                f"Failed to transcribe video {video_id} using Whisper: {str(e)}"
            )
            raise Exception(
                f"Whisper transcription failed for video {video_id}: {str(e)}"
            )

        finally:
            # Cleanup temporary files
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    logger.debug(f"Cleaned up temporary directory: {temp_dir}")
                except Exception as cleanup_error:
                    logger.warning(
                        f"Failed to cleanup temporary directory: {cleanup_error}"
                    )

    def _transcribe_single_file(self, audio_path: str, video_id: str) -> str:
        """Transcribe a single audio file using OpenAI Whisper."""
        logger.info(f"Transcribing audio using OpenAI Whisper for video: {video_id}")

        with open(audio_path, "rb") as audio_file:
            transcript_response = self.client.audio.transcriptions.create(
                model="whisper-1", file=audio_file, response_format="text"
            )

        logger.info(f"Successfully transcribed video {video_id} using OpenAI Whisper")
        return transcript_response

    def _transcribe_large_file(
        self, audio_path: str, video_id: str, temp_dir: str
    ) -> str:
        """Split large audio file into chunks and transcribe each chunk."""
        try:
            chunks = self._split_audio_file(audio_path, video_id, temp_dir)

            # Transcribe each chunk
            all_transcripts = []
            for i, chunk_path in enumerate(chunks):
                logger.info(f"Transcribing chunk {i + 1}/{len(chunks)}")

                with open(chunk_path, "rb") as audio_file:
                    transcript_response = self.client.audio.transcriptions.create(
                        model="whisper-1", file=audio_file, response_format="text"
                    )

                all_transcripts.append(transcript_response)
                logger.info(f"Completed chunk {i + 1}/{len(chunks)}")

            # Combine all transcripts
            full_transcript = " ".join(all_transcripts)
            logger.info(
                f"Successfully transcribed {len(chunks)} chunks for video {video_id}"
            )

            return full_transcript

        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error while processing large file: {e}")
            raise Exception(f"Audio processing failed: {e}")
        except Exception as e:
            logger.error(f"Error transcribing large file: {e}")
            raise

    def _split_audio_file(self, audio_path: str, video_id: str, temp_dir: str) -> list:
        """Split audio file into chunks using FFmpeg."""
        chunks = []

        # Get audio duration first
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                audio_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        total_duration = float(result.stdout.strip())
        logger.info(f"Total audio duration: {total_duration:.1f} seconds")

        # Split into chunks
        chunk_count = 0
        for start_time in range(0, int(total_duration), self.chunk_duration):
            chunk_path = os.path.join(temp_dir, f"{video_id}_chunk_{chunk_count}.mp3")

            # Use FFmpeg to extract chunk
            subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    audio_path,
                    "-ss",
                    str(start_time),
                    "-t",
                    str(self.chunk_duration),
                    "-acodec",
                    "copy",
                    chunk_path,
                    "-y",
                ],
                check=True,
                capture_output=True,
            )

            chunks.append(chunk_path)
            chunk_count += 1
            logger.info(
                f"Created chunk {chunk_count}: {start_time}s-{start_time + self.chunk_duration}s"
            )

        return chunks
