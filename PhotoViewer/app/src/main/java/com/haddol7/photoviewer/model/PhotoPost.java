package com.haddol7.photoviewer.model;

public final class PhotoPost {
    public final long id, authorId;
    public final String title, text, imageUrl, created, published;

    public PhotoPost(long id, long authorId, String title, String text, String imageUrl,
                     String created, String published) {
        this.id = id; this.authorId = authorId; this.title = title; this.text = text;
        this.imageUrl = imageUrl; this.created = created; this.published = published;
    }
}
