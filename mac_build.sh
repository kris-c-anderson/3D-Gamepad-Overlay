#! /bin/sh
# Needs SDL 3.4.x (brew install sdl3) and GLFW (brew install glfw).
bear -- g++ -std=c++17 -g -Wall src/glad.c src/imgui/*.cpp src/*.cpp -o mac_prog -I include -I src/imgui -L lib -L /opt/homebrew/lib -L /usr/local/lib -lglfw -lSDL3 -framework OpenGL -ldl
