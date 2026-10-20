#if defined(__linux__) 
#elif __FreeBSD__
#elif __ANDROID__
#elif __APPLE__
#elif _WIN32
#define SDL_MAIN_HANDLED
#else //some other operating system
#endif

#include "settings_window.h"

bool gQuit = false;

void InitializeProgram(){
	// The overlay is almost never the focused window (the game is), so keep
	// receiving controller input while in the background.
	SDL_SetHint(SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, "1");
	// Make sure SDL's own HIDAPI drivers are used for Valve hardware
	// (Steam Controller 2026 / "Triton", incl. the Puck dongle) so we get
	// gyro, both trackpads, grip buttons and capacitive touch.
	SDL_SetHint(SDL_HINT_JOYSTICK_HIDAPI, "1");
	SDL_SetHint(SDL_HINT_JOYSTICK_HIDAPI_STEAM, "1");

	if(!SDL_Init(SDL_INIT_JOYSTICK | SDL_INIT_GAMEPAD | SDL_INIT_SENSOR)){
        printf("Error: %s\n", SDL_GetError());
        exit(1);
    }
	
	createSettingsWindow();

	loadTabs();
}

void Input(){
	glfwPollEvents();
	
	settings_window_input(gQuit);
	controller_window_input();
	
	SDL_Event event;
	while (SDL_PollEvent(&event)){
    	settings_sdl_events(&event);	
		controller_sdl_events(&event);
	}
}

void Draw(){
	drawSettingsWindow();
	drawControllerWindows();
}

void MainLoop(){
	while(!gQuit){
		Input();

		Draw();
	}
}

void Cleanup(){
	saveTabs();

	removeSettingsWindow();
	
	destroyWindows();
	
	SDL_Quit();

	glfwTerminate();
}

int main(){
	InitializeProgram();
	
	MainLoop();

	Cleanup();

	return 0;
}
