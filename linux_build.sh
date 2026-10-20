#! /bin/sh
# Needs SDL 3.4.x (for Steam Controller 2026 support) and GLFW 3 development packages.
bear -- g++ -std=c++17 -g -Wall src/glad.c src/imgui/*.cpp src/*.cpp -o 3dco -I include -I src/imgui -lglfw -lSDL3 -lGL -ldl
