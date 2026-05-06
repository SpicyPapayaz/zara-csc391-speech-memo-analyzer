# Voice-Powered Memo Analyzer

## Overview

This project is a voice-powered memo analyzer built with Flask and deployed on Azure App Service. The application allows a user to record a short spoken memo directly in the browser or upload a WAV audio file. The backend sends the audio to Azure Speech-to-Text, analyzes the transcript with Azure AI Language, and generates a spoken summary using Azure Text-to-Speech.

The app includes a browser frontend, Flask backend, Azure Speech integration, Azure Language integration, and a `/telemetry-summary` endpoint that reports basic session telemetry such as confidence scores, entity count, sentiment, and stage timing.

## Architecture

The application follows this pipeline:

```text
Browser microphone recording or WAV upload
        ↓
Flask backend /process endpoint
        ↓
Azure Speech-to-Text
        ↓
Azure AI Language Analysis
        ↓
Azure Text-to-Speech
        ↓
Browser displays transcript, key phrases, entities, sentiment, raw JSON, and playable TTS summary
