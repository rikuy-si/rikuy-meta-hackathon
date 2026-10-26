# Rikuy Connect

One safe connection layer that lets AI agents see through any camera in the world.

## Built during the hackathon

This repository was created on October 26, 2026 for the Meta Global AI Developer Hackathon (Cerebral Valley x Meta, Oct 26 - Nov 4, 2026). All code in this repository was written during the event. Pre-existing work: none in this repository.

## What we are building

Rikuy Connect is a local gateway that turns any camera (RTSP/ONVIF cameras, Hikvision/HiLook DVR/NVRs, phone and webcams over WebRTC) into one interface that AI agents can use, with permissions, audit and revocation.

## Planned architecture

- Local gateway with connectors: RTSP/ONVIF, Hikvision/HiLook ISAPI, WebRTC for phones and webcams.
- REST and MCP contract for agents, with grants, audit log and revocation.
- Meta AI: Muse Spark as the agent, SAM 3.1 for face anonymization and text search across cameras, Muse Spark Open on Baseten for cheap triage.

## Status

Day 0. Work in progress.
