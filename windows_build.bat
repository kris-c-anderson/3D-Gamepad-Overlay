g++ -std=c++17 -O2 -mwindows -Wall src/glad.c src/imgui/*.cpp src/*.cpp -I include -I src/imgui -o 3dco 3dco.res -static lib/libSDL3.dll.a -L lib -lglfw3 -lgdi32 -lopengl32
