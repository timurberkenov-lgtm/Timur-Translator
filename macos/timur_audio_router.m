#import <Foundation/Foundation.h>
#import <CoreAudio/CoreAudio.h>

static NSString * const RouteName = @"Timur Translator Output";
static NSString * const RouteUID = @"com.timur.translator.autoroute";

static AudioObjectPropertyAddress Address(AudioObjectPropertySelector selector, AudioObjectPropertyScope scope) {
    AudioObjectPropertyAddress address = { selector, scope, kAudioObjectPropertyElementMain };
    return address;
}

static NSString *StatePath(void) {
    NSString *dir = [NSHomeDirectory() stringByAppendingPathComponent:@".timur_translator_realtime"];
    [[NSFileManager defaultManager] createDirectoryAtPath:dir withIntermediateDirectories:YES attributes:nil error:nil];
    return [dir stringByAppendingPathComponent:@"macos_audio_route.json"];
}

static void PrintJSON(NSDictionary *payload, int exitCode) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:payload options:0 error:nil];
    NSString *json = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
    fprintf(stdout, "%s\n", json.UTF8String ?: "{}");
    exit(exitCode);
}

static NSString *FourCC(OSStatus status) {
    UInt32 value = CFSwapInt32HostToBig((UInt32)status);
    char chars[5] = {0};
    memcpy(chars, &value, 4);
    for (int i = 0; i < 4; i++) {
        if (chars[i] < 32 || chars[i] > 126) return [NSString stringWithFormat:@"%d", (int)status];
    }
    return [NSString stringWithFormat:@"'%s'", chars];
}

static NSString *StringProperty(AudioObjectID objectID, AudioObjectPropertySelector selector) {
    AudioObjectPropertyAddress address = Address(selector, kAudioObjectPropertyScopeGlobal);
    CFStringRef value = NULL;
    UInt32 size = sizeof(value);
    OSStatus status = AudioObjectGetPropertyData(objectID, &address, 0, NULL, &size, &value);
    if (status != noErr || value == NULL) return @"";
    return CFBridgingRelease(value);
}

static UInt32 UInt32Property(AudioObjectID objectID, AudioObjectPropertySelector selector, UInt32 fallback) {
    AudioObjectPropertyAddress address = Address(selector, kAudioObjectPropertyScopeGlobal);
    UInt32 value = fallback;
    UInt32 size = sizeof(value);
    OSStatus status = AudioObjectGetPropertyData(objectID, &address, 0, NULL, &size, &value);
    return status == noErr ? value : fallback;
}

static UInt32 OutputChannels(AudioObjectID objectID) {
    AudioObjectPropertyAddress address = Address(kAudioDevicePropertyStreamConfiguration, kAudioDevicePropertyScopeOutput);
    UInt32 size = 0;
    if (AudioObjectGetPropertyDataSize(objectID, &address, 0, NULL, &size) != noErr || size == 0) return 0;
    AudioBufferList *list = (AudioBufferList *)calloc(1, size);
    if (!list) return 0;
    UInt32 channels = 0;
    if (AudioObjectGetPropertyData(objectID, &address, 0, NULL, &size, list) == noErr) {
        for (UInt32 index = 0; index < list->mNumberBuffers; index++) channels += list->mBuffers[index].mNumberChannels;
    }
    free(list);
    return channels;
}

static NSArray<NSDictionary *> *AudioDevices(void) {
    AudioObjectPropertyAddress address = Address(kAudioHardwarePropertyDevices, kAudioObjectPropertyScopeGlobal);
    UInt32 size = 0;
    if (AudioObjectGetPropertyDataSize(kAudioObjectSystemObject, &address, 0, NULL, &size) != noErr || size == 0) return @[];
    UInt32 count = size / sizeof(AudioObjectID);
    AudioObjectID *ids = (AudioObjectID *)calloc(count, sizeof(AudioObjectID));
    if (!ids) return @[];
    if (AudioObjectGetPropertyData(kAudioObjectSystemObject, &address, 0, NULL, &size, ids) != noErr) {
        free(ids);
        return @[];
    }
    NSMutableArray *devices = [NSMutableArray array];
    for (UInt32 index = 0; index < count; index++) {
        AudioObjectID objectID = ids[index];
        NSString *name = StringProperty(objectID, kAudioObjectPropertyName);
        NSString *uid = StringProperty(objectID, kAudioDevicePropertyDeviceUID);
        UInt32 classID = UInt32Property(objectID, kAudioObjectPropertyClass, 0);
        UInt32 alive = UInt32Property(objectID, kAudioDevicePropertyDeviceIsAlive, 1);
        UInt32 transport = UInt32Property(objectID, kAudioDevicePropertyTransportType, 0);
        UInt32 outputs = OutputChannels(objectID);
        if (uid.length == 0) continue;
        [devices addObject:@{
            @"id": @(objectID), @"name": name ?: @"", @"uid": uid,
            @"class": @(classID), @"alive": @(alive), @"transport": @(transport), @"outputs": @(outputs)
        }];
    }
    free(ids);
    return devices;
}

static AudioObjectID DefaultOutput(void) {
    AudioObjectPropertyAddress address = Address(kAudioHardwarePropertyDefaultOutputDevice, kAudioObjectPropertyScopeGlobal);
    AudioObjectID deviceID = kAudioObjectUnknown;
    UInt32 size = sizeof(deviceID);
    AudioObjectGetPropertyData(kAudioObjectSystemObject, &address, 0, NULL, &size, &deviceID);
    return deviceID;
}

static BOOL SetDefaultOutput(AudioObjectID deviceID, NSString **error) {
    AudioObjectPropertyAddress address = Address(kAudioHardwarePropertyDefaultOutputDevice, kAudioObjectPropertyScopeGlobal);
    UInt32 size = sizeof(deviceID);
    OSStatus status = AudioObjectSetPropertyData(kAudioObjectSystemObject, &address, 0, NULL, size, &deviceID);
    if (status != noErr) {
        if (error) *error = [NSString stringWithFormat:@"Could not set default output (%@)", FourCC(status)];
        return NO;
    }
    // Sound effects do not affect interview audio. Update them on a best-effort
    // basis because some macOS versions reject aggregate devices for alerts.
    address = Address(kAudioHardwarePropertyDefaultSystemOutputDevice, kAudioObjectPropertyScopeGlobal);
    AudioObjectSetPropertyData(kAudioObjectSystemObject, &address, 0, NULL, size, &deviceID);
    return YES;
}

static NSDictionary *ReadState(void) {
    NSData *data = [NSData dataWithContentsOfFile:StatePath()];
    if (!data) return @{};
    NSDictionary *state = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    return [state isKindOfClass:[NSDictionary class]] ? state : @{};
}

static void WriteState(NSString *physicalUID, NSString *physicalName) {
    NSDictionary *state = @{ @"physical_uid": physicalUID ?: @"", @"physical_name": physicalName ?: @"" };
    NSData *data = [NSJSONSerialization dataWithJSONObject:state options:NSJSONWritingPrettyPrinted error:nil];
    [data writeToFile:StatePath() atomically:YES];
}

static NSDictionary *DeviceByUID(NSArray<NSDictionary *> *devices, NSString *uid) {
    for (NSDictionary *device in devices) if ([device[@"uid"] isEqualToString:uid]) return device;
    return nil;
}

static NSDictionary *DeviceByID(NSArray<NSDictionary *> *devices, AudioObjectID objectID) {
    for (NSDictionary *device in devices) if ([device[@"id"] unsignedIntValue] == objectID) return device;
    return nil;
}

static BOOL ContainsAny(NSString *name, NSArray<NSString *> *needles) {
    NSString *lower = name.lowercaseString;
    for (NSString *needle in needles) if ([lower containsString:needle]) return YES;
    return NO;
}

static BOOL IsBlackHole(NSDictionary *device) {
    return ContainsAny(device[@"name"], @[ @"blackhole" ]);
}

static BOOL IsRoute(NSDictionary *device) {
    return [device[@"uid"] isEqualToString:RouteUID] || [device[@"name"] isEqualToString:RouteName];
}

static BOOL IsUsablePhysicalOutput(NSDictionary *device) {
    if ([device[@"outputs"] unsignedIntValue] < 1 || [device[@"alive"] unsignedIntValue] == 0) return NO;
    if (IsBlackHole(device) || IsRoute(device)) return NO;
    if ([device[@"class"] unsignedIntValue] == kAudioAggregateDeviceClassID) return NO;
    if (ContainsAny(device[@"name"], @[ @"multi-output", @"aggregate", @"soundflower", @"loopback", @"virtual", @"microsoft teams" ])) return NO;
    return YES;
}

static NSInteger PhysicalScore(NSDictionary *device) {
    NSString *name = [device[@"name"] lowercaseString];
    NSInteger score = 0;
    if (ContainsAny(name, @[ @"headphone", @"headphones", @"headset", @"airpods", @"buds", @"earbuds", @"bluetooth", @"usb", @"external" ])) score += 100;
    if (ContainsAny(name, @[ @"speaker", @"speakers", @"built-in", @"macbook" ])) score += 10;
    return score;
}

static NSDictionary *ChoosePhysical(NSArray<NSDictionary *> *devices, NSDictionary *state) {
    NSDictionary *defaultDevice = DeviceByID(devices, DefaultOutput());
    NSString *savedUID = state[@"physical_uid"];
    NSDictionary *saved = savedUID.length ? DeviceByUID(devices, savedUID) : nil;
    NSDictionary *best = nil;
    NSDictionary *bestHeadset = nil;
    NSInteger bestScore = NSIntegerMin;
    NSInteger bestHeadsetScore = NSIntegerMin;
    for (NSDictionary *device in devices) {
        if (!IsUsablePhysicalOutput(device)) continue;
        NSInteger score = PhysicalScore(device);
        if (saved && [device[@"uid"] isEqualToString:saved[@"uid"]]) score += 20;
        if (score > bestScore) { best = device; bestScore = score; }
        if (PhysicalScore(device) >= 100 && score > bestHeadsetScore) { bestHeadset = device; bestHeadsetScore = score; }
    }
    // Headphones win over built-in speakers even while the old aggregate route
    // is still selected. This is the macOS equivalent of Windows endpoint
    // following when a headset appears.
    if (bestHeadset) return bestHeadset;
    if (defaultDevice && IsUsablePhysicalOutput(defaultDevice)) return defaultDevice;
    if (saved && IsUsablePhysicalOutput(saved)) return saved;
    return best;
}

static BOOL DestroyRouteIfPresent(NSArray<NSDictionary *> *devices, NSString **error) {
    NSDictionary *route = DeviceByUID(devices, RouteUID);
    if (!route) return YES;
    AudioObjectID routeID = [route[@"id"] unsignedIntValue];
    OSStatus status = AudioHardwareDestroyAggregateDevice(routeID);
    if (status != noErr) {
        if (error) *error = [NSString stringWithFormat:@"Could not destroy old route (%@)", FourCC(status)];
        return NO;
    }
    [NSThread sleepForTimeInterval:0.12];
    return YES;
}

static AudioObjectID CreateRoute(NSDictionary *physical, NSDictionary *blackHole, NSString **error) {
    NSString *physicalUID = physical[@"uid"];
    NSString *blackHoleUID = blackHole[@"uid"];
    NSDictionary *description = @{
        @"name": RouteName,
        @"uid": RouteUID,
        @"private": @NO,
        @"stacked": @NO,
        @"master": physicalUID,
        @"subdevices": @[
            @{ @"uid": physicalUID, @"drift": @NO },
            @{ @"uid": blackHoleUID, @"drift": @YES }
        ]
    };
    AudioObjectID aggregateID = kAudioObjectUnknown;
    OSStatus status = AudioHardwareCreateAggregateDevice((__bridge CFDictionaryRef)description, &aggregateID);
    if (status != noErr) {
        if (error) *error = [NSString stringWithFormat:@"Could not create multi-output route (%@)", FourCC(status)];
        return kAudioObjectUnknown;
    }
    [NSThread sleepForTimeInterval:0.18];
    return aggregateID;
}

static NSDictionary *EnsureRoute(void) {
    NSArray<NSDictionary *> *devices = AudioDevices();
    NSDictionary *state = ReadState();
    NSDictionary *blackHole = nil;
    for (NSDictionary *device in devices) if (IsBlackHole(device) && [device[@"outputs"] unsignedIntValue] > 0) { blackHole = device; break; }
    if (!blackHole) return @{ @"ok": @NO, @"error": @"BlackHole 2ch output was not found" };
    NSDictionary *physical = ChoosePhysical(devices, state);
    if (!physical) return @{ @"ok": @NO, @"error": @"No physical speaker or headphone output was found" };

    NSDictionary *route = DeviceByUID(devices, RouteUID);
    NSString *savedUID = state[@"physical_uid"] ?: @"";
    BOOL needsRebuild = !route || ![savedUID isEqualToString:physical[@"uid"]];
    NSString *error = nil;
    BOOL changed = NO;
    if (needsRebuild) {
        if (route) {
            SetDefaultOutput([physical[@"id"] unsignedIntValue], nil);
            if (!DestroyRouteIfPresent(devices, &error)) return @{ @"ok": @NO, @"error": error ?: @"Could not replace old route" };
        }
        AudioObjectID routeID = CreateRoute(physical, blackHole, &error);
        if (routeID == kAudioObjectUnknown) return @{ @"ok": @NO, @"error": error ?: @"Could not create route" };
        route = @{ @"id": @(routeID), @"uid": RouteUID, @"name": RouteName };
        changed = YES;
    }
    if (DefaultOutput() != [route[@"id"] unsignedIntValue]) {
        if (!SetDefaultOutput([route[@"id"] unsignedIntValue], &error)) return @{ @"ok": @NO, @"error": error ?: @"Could not activate route" };
        changed = YES;
    }
    WriteState(physical[@"uid"], physical[@"name"]);
    return @{ @"ok": @YES, @"changed": @(changed), @"route": RouteName, @"physical": physical[@"name"], @"blackhole": blackHole[@"name"] };
}

static NSDictionary *RestoreRoute(void) {
    NSArray<NSDictionary *> *devices = AudioDevices();
    NSDictionary *state = ReadState();
    NSDictionary *physical = DeviceByUID(devices, state[@"physical_uid"] ?: @"");
    if (!physical || !IsUsablePhysicalOutput(physical)) physical = ChoosePhysical(devices, @{});
    NSString *error = nil;
    if (physical) SetDefaultOutput([physical[@"id"] unsignedIntValue], &error);
    DestroyRouteIfPresent(devices, nil);
    return @{ @"ok": @YES, @"restored": physical[@"name"] ?: @"" };
}

int main(int argc, const char * argv[]) {
    @autoreleasepool {
        NSString *command = argc > 1 ? [NSString stringWithUTF8String:argv[1]] : @"ensure";
        NSDictionary *result = [command isEqualToString:@"restore"] ? RestoreRoute() : EnsureRoute();
        PrintJSON(result, [result[@"ok"] boolValue] ? 0 : 1);
    }
}
