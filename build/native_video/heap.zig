pub const GeneralPurposeAllocator = @import("heap/GeneralPurposeAllocator.zig");

pub const engine_allocator: Allocator = .{
    .ptr = undefined,
    .vtable = &.{
        .alloc = @ptrCast(&alloc),
        .resize = @ptrCast(&resize),
        .remap = @ptrCast(&remap),
        .free = @ptrCast(&free),
    },
};

fn alloc(_: *anyopaque, len: usize, alignment: Alignment, _: usize) ?[*]u8 {
    if (alignment == .@"1") {
        return @ptrCast(raw.memAlloc(len) orelse return null);
    }

    // The payload starts at forward(block + 4), up to 4 + alignment - 1 bytes into the block, so the block
    // needs alignment + 4 extra bytes (upstream reserved only alignment: the tail of the payload overran it).
    const padding = alignment.toByteUnits() + @sizeOf(u32);
    const unaligned_ptr = raw.memAlloc(len + padding) orelse return null;
    const unaligned_addr = @intFromPtr(unaligned_ptr);
    const aligned_addr = alignment.forward(unaligned_addr + @sizeOf(u32));

    @as(*align(1) u32, @ptrFromInt(aligned_addr - @sizeOf(u32))).* = @intCast(aligned_addr - unaligned_addr);

    return @ptrFromInt(aligned_addr);
}

fn resize(_: *anyopaque, _: []u8, _: Alignment, _: usize, _: usize) bool {
    return false;
}

fn remap(_: *anyopaque, memory: []u8, alignment: Alignment, new_len: usize, _: usize) ?[*]u8 {
    if (alignment == .@"1") {
        return @ptrCast(raw.memRealloc(memory.ptr, new_len) orelse return null);
    }

    const padding = alignment.toByteUnits() + @sizeOf(u32);
    const aligned_addr = @intFromPtr(memory.ptr);
    const offset = @as(*align(1) u32, @ptrFromInt(aligned_addr - @sizeOf(u32))).*;

    const new_unaligned_ptr = raw.memRealloc(@ptrFromInt(aligned_addr - offset), new_len + padding) orelse return null;
    const new_unaligned_addr = @intFromPtr(new_unaligned_ptr);
    const new_aligned_addr = alignment.forward(new_unaligned_addr + @sizeOf(u32));

    // realloc keeps the bytes at the old offset; the new block may align differently, so move the payload.
    const new_offset = new_aligned_addr - new_unaligned_addr;
    if (new_offset != offset) {
        const keep = @min(memory.len, new_len);
        const src: [*]u8 = @ptrFromInt(new_unaligned_addr + offset);
        const dst: [*]u8 = @ptrFromInt(new_aligned_addr);
        if (new_offset < offset) std.mem.copyForwards(u8, dst[0..keep], src[0..keep]) else std.mem.copyBackwards(u8, dst[0..keep], src[0..keep]);
    }

    @as(*align(1) u32, @ptrFromInt(new_aligned_addr - @sizeOf(u32))).* = @intCast(new_aligned_addr - new_unaligned_addr);

    return @ptrFromInt(new_aligned_addr);
}

fn free(_: *anyopaque, memory: []u8, alignment: Alignment, _: usize) void {
    if (alignment == .@"1") {
        raw.memFree(memory.ptr);
        return;
    }

    const aligned_addr = @intFromPtr(memory.ptr);
    const offset = @as(*align(1) u32, @ptrFromInt(aligned_addr - @sizeOf(u32))).*;

    raw.memFree(@ptrFromInt(aligned_addr - offset));
}

const std = @import("std");
const Alignment = std.mem.Alignment;
const Allocator = std.mem.Allocator;

const gdzig = @import("gdzig");
const raw = &gdzig.raw;
